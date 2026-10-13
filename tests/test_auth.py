"""Tests for auth endpoint — login, logout, rate limiting, session gate."""

import hashlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import sunny.auth
from sunny.auth import hash_password, verify_password
from sunny.main import create_app


@pytest.fixture(autouse=True)
def _reset_auth_state():
    sunny.auth._login_attempts.clear()
    sunny.auth._revoked.clear()
    with patch.object(sunny.auth, "_session_secret", return_value=b"test-secret"):
        yield
    sunny.auth._login_attempts.clear()


@pytest.fixture()
def client():
    return TestClient(create_app(), base_url="https://testserver")


class TestPasswordHash:
    def test_pbkdf2_roundtrip(self):
        stored = hash_password("correct horse", iterations=1000)
        assert stored.startswith("pbkdf2_sha256:1000:")
        assert verify_password("correct horse", stored)
        assert not verify_password("wrong", stored)

    def test_salted(self):
        assert hash_password("same", iterations=1000) != hash_password("same", iterations=1000)

    def test_legacy_sha256(self):
        legacy = hashlib.sha256(b"correct").hexdigest()
        assert verify_password("correct", legacy)
        assert not verify_password("nope", legacy)

    def test_malformed_hash_rejects(self):
        assert not verify_password("x", "pbkdf2_sha256:notanumber")


class TestLogin:
    def test_login_unconfigured_allows_any_password(self, client):
        """When admin_password_hash is empty (dev), login accepts any non-empty password."""
        with patch("sunny.auth._get_admin_hash", return_value=""):
            resp = client.post("/login", json={"password": "anything"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_login_with_valid_password(self, client):
        stored = hash_password("correct", iterations=1000)
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            resp = client.post("/login", json={"password": "correct"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_login_rejects_bad_password(self, client):
        stored = hash_password("correct", iterations=1000)
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            resp = client.post("/login", json={"password": "wrong"})
            assert resp.status_code == 401

    def test_login_rejects_pass_the_hash(self, client):
        """Sending the stored hash itself must not authenticate."""
        stored = hashlib.sha256(b"correct").hexdigest()
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            resp = client.post("/login", json={"password_hash": stored})
            assert resp.status_code == 400

    def test_login_returns_session_cookie(self, client):
        """Login success sets a session cookie with HttpOnly and SameSite=Strict."""
        with patch("sunny.auth._get_admin_hash", return_value=""):
            resp = client.post("/login", json={"password": "test"})
            assert resp.status_code == 200
            set_cookie = resp.headers.get("set-cookie", "")
            assert "HttpOnly" in set_cookie
            assert "samesite=strict" in set_cookie.lower()
            assert "Secure" in set_cookie

    def test_login_rejects_empty_credentials(self, client):
        """Login with no password returns 400."""
        resp = client.post("/login", json={})
        assert resp.status_code == 400


class TestLogout:
    def test_logout_clears_cookie(self, client):
        resp = client.post("/logout")
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "")
        assert "Max-Age=0" in set_cookie

    def test_logout_revokes_token(self, client):
        stored = hash_password("pw", iterations=1000)
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            client.post("/login", json={"password": "pw"})
            assert client.get("/auth/status").json()["authenticated"] is True
            token = client.cookies.get("session")
            client.post("/logout")
            client.cookies.set("session", token)
            assert client.get("/auth/status").json()["authenticated"] is False


class TestAuthStatus:
    def test_unauthenticated_returns_false(self, client):
        resp = client.get("/auth/status")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is False

    def test_authenticated_after_login(self, client):
        stored = hash_password("pw", iterations=1000)
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            client.post("/login", json={"password": "pw"})
            assert client.get("/auth/status").json()["authenticated"] is True

    def test_tampered_token_rejected(self, client):
        token = sunny.auth._create_session()
        expires, nonce, sig = token.split(".")
        client.cookies.set("session", f"{int(expires) + 999}.{nonce}.{sig}")
        assert client.get("/auth/status").json()["authenticated"] is False

    def test_expired_token_rejected(self, client):
        client.cookies.set("session", sunny.auth._create_session(max_age_hours=-1))
        assert client.get("/auth/status").json()["authenticated"] is False


class TestGate:
    def test_api_requires_session_when_configured(self, client):
        stored = hash_password("pw", iterations=1000)
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            assert client.get("/projects").status_code == 401
            client.post("/login", json={"password": "pw"})
            assert client.get("/projects").status_code == 200

    def test_public_paths_open(self, client):
        stored = hash_password("pw", iterations=1000)
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            assert client.get("/health").status_code == 200
            assert client.get("/auth/status").status_code == 200

    def test_cross_origin_write_rejected(self, client):
        resp = client.post("/login", json={"password": "x"}, headers={"Origin": "https://evil.example"})
        assert resp.status_code == 403

    def test_same_origin_write_allowed(self, client):
        with patch("sunny.auth._get_admin_hash", return_value=""):
            resp = client.post("/login", json={"password": "x"}, headers={"Origin": "https://testserver"})
            assert resp.status_code == 200


class TestRateLimit:
    def test_rate_limits_after_max_attempts(self):
        """After 5 failed attempts from same IP, login should be rate-limited."""
        stored = hash_password("real", iterations=1000)
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            for i in range(5):
                resp = TestClient(create_app()).post("/login", json={"password": "bad"})
                assert resp.status_code == 401, f"Attempt {i} should be 401, got {resp.status_code}"

            # 6th attempt should be rate limited
            resp = TestClient(create_app()).post("/login", json={"password": "bad"})
            assert resp.status_code == 429
            assert "Too many" in resp.json()["detail"]


class TestSlidingSession:
    def test_old_session_is_renewed(self, client):
        stored = hash_password("pw", iterations=1000)
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            client.cookies.set("session", sunny.auth._create_session(max_age_hours=1))  # < half of 720h left
            resp = client.get("/auth/status")
            assert resp.json()["authenticated"] is True
            assert "session=" in resp.headers.get("set-cookie", "")

    def test_fresh_session_not_reissued(self, client):
        stored = hash_password("pw", iterations=1000)
        with patch("sunny.auth._get_admin_hash", return_value=stored):
            client.cookies.set("session", sunny.auth._create_session())
            resp = client.get("/auth/status")
            assert "set-cookie" not in resp.headers
