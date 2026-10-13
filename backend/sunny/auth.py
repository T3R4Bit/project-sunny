"""Auth — login hardening: password hash, rate limit, SameSite cookie, Origin check.

Password hashes are ``pbkdf2_sha256:<iterations>:<salt hex>:<hash hex>`` (generate one with
``python -m sunny.auth``). A bare 64-char SHA-256 hex digest is still accepted for older .env files.

Session cookies are stateless HMAC-signed tokens (``<expires>.<nonce>.<sig>``) so they survive
restarts. The signing key comes from ``SESSION_SECRET`` or, failing that, a random key persisted
in ``<secret_dir>/session_secret``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from sunny import config

log = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

COOKIE_NAME = "session"
PBKDF2_ITERATIONS = 600_000

# Paths reachable without a session: auth itself, health, and the static PWA shell.
PUBLIC_PATHS = {"/login", "/logout", "/auth/status", "/health", "/", "/index.html", "/auth/google/callback",
                "/manifest.json", "/sw.js", "/favicon.ico"}
PUBLIC_PREFIXES = ("/assets/", "/icon-")

# --- In-memory rate limiter ---

_login_attempts: dict[str, list[float]] = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300  # 5 minutes


def _check_rate_limit(ip: str) -> Optional[str]:
    """Return lockout reason string, or None if allowed."""
    now = time.time()
    if ip not in _login_attempts:
        _login_attempts[ip] = []

    # Prune old attempts
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _LOCKOUT_SECONDS]

    if len(_login_attempts[ip]) >= _MAX_ATTEMPTS:
        return f"Too many login attempts. Try again in {int(_LOCKOUT_SECONDS - (now - _login_attempts[ip][0]))}s"
    return None


def _record_attempt(ip: str, success: bool) -> None:
    """Record a login attempt."""
    now = time.time()
    if ip not in _login_attempts:
        _login_attempts[ip] = []
    _login_attempts[ip].append(now)
    if success:
        _login_attempts[ip] = []  # reset on success


# --- Password hashing ---


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Return a salted PBKDF2-SHA256 hash string for ADMIN_PASSWORD_HASH."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256:{iterations}:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash (PBKDF2 format or legacy bare SHA-256 hex)."""
    if stored.startswith("pbkdf2_sha256:"):
        try:
            _, iterations, salt_hex, hash_hex = stored.split(":")
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        except ValueError:
            log.error("ADMIN_PASSWORD_HASH is malformed")
            return False
        return hmac.compare_digest(digest.hex(), hash_hex)
    computed = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(computed, stored.lower())


# --- Session tokens ---

_revoked: set[str] = set()
_cached_secret: Optional[bytes] = None


def _session_secret() -> bytes:
    """Signing key: SESSION_SECRET env, else a random key persisted in the secrets dir."""
    global _cached_secret
    settings = config.get_settings()
    if settings.session_secret:
        return settings.session_secret.encode()
    if _cached_secret is not None:
        return _cached_secret
    path = Path(settings.secret_dir) / "session_secret"
    try:
        if path.exists():
            _cached_secret = path.read_text().strip().encode()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            value = secrets.token_urlsafe(48)
            path.write_text(value)
            path.chmod(0o600)
            _cached_secret = value.encode()
    except OSError as e:
        log.warning("Cannot persist session secret (%s); sessions will reset on restart", e)
        _cached_secret = secrets.token_urlsafe(48).encode()
    return _cached_secret


def _sign(payload: str) -> str:
    return hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()


def _create_session(max_age_hours: int = 720) -> str:
    """Create a new signed session token."""
    expires = int(time.time()) + max_age_hours * 3600
    payload = f"{expires}.{secrets.token_urlsafe(16)}"
    return f"{payload}.{_sign(payload)}"


def _get_session(request: Request) -> Optional[str]:
    """Extract session token from cookie."""
    return request.cookies.get(COOKIE_NAME) or None


def _validate_session(token: Optional[str]) -> bool:
    """Check that a session token is correctly signed, unexpired and not revoked."""
    if not token or token in _revoked:
        return False
    try:
        expires, nonce, sig = token.split(".")
        expired = time.time() > int(expires)
    except ValueError:
        return False
    if expired:
        return False
    return hmac.compare_digest(sig, _sign(f"{expires}.{nonce}"))


def _cookie_max_age() -> int:
    return config.get_settings().session_max_age_hours * 3600


@router.post("/login")
async def login(request: Request) -> JSONResponse:
    """Authenticate with the admin password. Returns session cookie on success."""
    ip = _get_client_ip(request)

    # Rate limit check
    lockout = _check_rate_limit(ip)
    if lockout:
        log.warning("Rate limited login from %s: %s", ip, lockout)
        raise HTTPException(status_code=429, detail=lockout)

    try:
        body = await request.json()
    except ValueError:
        body = {}
    password = body.get("password", "") if isinstance(body, dict) else ""

    if not password:
        _record_attempt(ip, False)
        raise HTTPException(status_code=400, detail="password required")

    admin_hash = _get_admin_hash()
    if not admin_hash:
        # Auth not configured (dev only) — accept any non-empty password
        valid = True
    else:
        valid = verify_password(password, admin_hash)

    if not valid:
        _record_attempt(ip, False)
        log.warning("Failed login from %s", ip)
        raise HTTPException(status_code=401, detail="invalid credentials")

    _record_attempt(ip, True)

    resp = JSONResponse(content={"status": "ok"})
    resp.set_cookie(
        COOKIE_NAME,
        value=_create_session(config.get_settings().session_max_age_hours),
        httponly=True,
        samesite="strict",
        max_age=_cookie_max_age(),
        secure=True,
        path="/",
    )
    return resp


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Invalidate the current session."""
    token = _get_session(request)
    if token:
        _revoked.add(token)
    resp = JSONResponse(content={"status": "ok"})
    resp.set_cookie(COOKIE_NAME, "", httponly=True, samesite="strict", max_age=0, secure=True, path="/")
    return resp


@router.get("/auth/status")
async def auth_status(request: Request) -> dict:
    """Check if currently authenticated."""
    return {"authenticated": _validate_session(_get_session(request))}


def _get_admin_hash() -> str:
    """Get the admin password hash from settings ("" means auth is not configured)."""
    return config.get_settings().admin_password_hash


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def verify_session(request: Request) -> bool:
    """True if the request carries a valid session, or auth is not configured (dev)."""
    if not _get_admin_hash():
        return True
    return _validate_session(_get_session(request))


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def _origin_ok(request: Request) -> bool:
    """Reject cross-origin state-changing requests (Origin host must match Host)."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    host = request.headers.get("host", "").split(":")[0]
    return urlparse(origin).hostname == host


def install_auth_middleware(app) -> None:
    """Require a valid session for every non-public path, plus an Origin check on writes."""

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        path = request.url.path
        if request.method not in ("GET", "HEAD", "OPTIONS") and not _origin_ok(request):
            return JSONResponse(status_code=403, content={"detail": "cross-origin request rejected"})
        if not _is_public(path) and not verify_session(request):
            return JSONResponse(status_code=401, content={"detail": "not authenticated"})
        response = await call_next(request)
        _maybe_renew(request, response)
        return response


def _maybe_renew(request: Request, response) -> None:
    """Sliding sessions: reissue the cookie once less than half its lifetime remains,
    so a device in regular use (e.g. the desk kiosk) never gets logged out."""
    token = _get_session(request)
    if not _validate_session(token):
        return
    max_age = _cookie_max_age()
    if int(token.split(".")[0]) - time.time() > max_age / 2:
        return
    response.set_cookie(COOKIE_NAME, value=_create_session(max_age // 3600), httponly=True,
                        samesite="strict", max_age=max_age, secure=True, path="/")


if __name__ == "__main__":
    import getpass

    pw = getpass.getpass("New Sunny password: ")
    if pw != getpass.getpass("Repeat: "):
        raise SystemExit("Passwords do not match")
    print(f"ADMIN_PASSWORD_HASH={hash_password(pw)}")
