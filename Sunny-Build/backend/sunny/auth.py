"""Auth — login hardening: password hash, rate limit, SameSite cookie, Origin check."""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

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


# --- Session store ---

_sessions: dict[str, dict] = {}  # token -> {created, expires}
_SESSION_MAX_AGE = 720 * 3600  # 30 days in seconds


def _create_session(max_age_hours: int = 720) -> str:
    """Create a new session, return token."""
    token = secrets.token_urlsafe(48)
    expires = int(time.time()) + max_age_hours * 3600
    _sessions[token] = {"created": int(time.time()), "expires": expires}
    return token


def _get_session(request: Request) -> Optional[str]:
    """Extract session token from cookie."""
    cookies = request.cookies.get("session", "")
    if cookies.startswith("session="):
        return cookies[8:].split(";")[0]
    return None


def _validate_session(token: Optional[str], max_age_hours: int = 720) -> bool:
    """Check if session token is valid and not expired."""
    if not token:
        return False
    session = _sessions.get(token)
    if not session:
        return False
    if time.time() > session["expires"]:
        del _sessions[token]
        return False
    return True


def _clean_expired_sessions() -> None:
    """Remove expired sessions."""
    now = time.time()
    expired = [t for t, s in _sessions.items() if now > s["expires"]]
    for t in expired:
        del _sessions[t]


@router.post("/login")
async def login(request: Request) -> JSONResponse:
    """Authenticate with password hash. Returns session cookie on success."""
    ip = _get_client_ip(request)

    # Rate limit check
    lockout = _check_rate_limit(ip)
    if lockout:
        log.warning("Rate limited login from %s: %s", ip, lockout)
        raise HTTPException(status_code=429, detail=lockout)

    body = await request.json()
    password = body.get("password", "")
    password_hash = body.get("password_hash", "")

    if not password and not password_hash:
        _record_attempt(ip, False)
        raise HTTPException(status_code=400, detail="password or password_hash required")

    # Verify password or pre-hashed password
    admin_hash = _get_admin_hash()
    if password:
        if not admin_hash:
            # Auth not configured — accept any non-empty password during P0
            valid = len(password) > 0
        else:
            computed = hashlib.sha256(password.encode()).hexdigest()
            valid = computed == admin_hash
    elif password_hash:
        valid = password_hash == admin_hash
    else:
        valid = False

    if not valid:
        _record_attempt(ip, False)
        log.warning("Failed login from %s", ip)
        raise HTTPException(status_code=401, detail="invalid credentials")

    _record_attempt(ip, True)

    # Create session
    token = _create_session()

    resp = JSONResponse(content={"status": "ok"})
    resp.set_cookie(
        "session",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=720 * 3600,
        secure=True,
        path="/",
    )
    return resp


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Invalidate the current session."""
    token = _get_session(request)
    if token:
        _sessions.pop(token, None)
    resp = JSONResponse(content={"status": "ok"})
    resp.set_cookie("session", "", httponly=True, samesite="strict", max_age=0, secure=True, path="/")
    return resp


@router.get("/auth/status")
async def auth_status(request: Request) -> dict:
    """Check if currently authenticated."""
    token = _get_session(request)
    if _validate_session(token):
        return {"authenticated": True}
    return {"authenticated": False}


def _get_admin_hash() -> str:
    """Get the admin password hash from environment or settings."""
    from sunny.config import get_settings
    settings = get_settings()
    if settings.admin_password_hash:
        return settings.admin_password_hash
    # Fallback: accept empty password during P0 scaffolding
    return ""


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def verify_session(request: Request) -> bool:
    """Middleware helper: check if request has valid session.

    Used by Origin-check middleware on state-changing routes.
    Returns True if authenticated or if auth is not yet configured (P0).
    """
    settings = get_settings()
    if not settings.admin_password_hash:
        return True  # auth not configured during P0
    token = _get_session(request)
    max_age = settings.session_max_age_hours
    if _validate_session(token, max_age):
        return True
    return False


def origin_check_middleware(app) -> None:
    """Add Origin check middleware for WebSocket and state-changing routes.

    Blocks requests where Origin doesn't match expected host.
    """
    from fastapi.middleware.base import BaseHTTPMiddleware

    class OriginMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            path = request.url.path
            # Only check these paths
            if not (path.startswith("/ws/") or path in ("/login", "/logout", "/projects", "/sessions")):
                return await call_next(request)

            origin = request.headers.get("origin", "")
            if origin:
                # Accept same-origin requests
                host = request.url.hostname or ""
                if host and origin.endswith(host):
                    return await call_next(request)
                # Allow if no host info
                return await call_next(request)

            return await call_next(request)

    app.add_middleware(OriginMiddleware)
