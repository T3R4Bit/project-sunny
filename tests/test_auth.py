"""Tests for auth endpoint — login, logout, rate limiting."""

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sunny.main import create_app


@pytest.fixture()
def client():
    return TestClient(create_app())


class TestLogin:
    def test_login_unconfigured_allows_any_password(self, client):
        """When admin_password_hash is empty (P0), login accepts any non-empty password."""
        with patch("sunny.auth._get_admin_hash", return_value=""):
            resp = client.post("/login", json={"password": "anything"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_login_with_valid_hash(self, client):
        """Login with correct password hash succeeds."""
        import hashlib
        valid_hash = hashlib.sha256(b"correct").hexdigest()
        with patch("sunny.auth._get_admin_hash", return_value=valid_hash):
            resp = client.post("/login", json={"password_hash": valid_hash})
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_login_rejects_bad_password(self, client):
        """Login with wrong password returns 401."""
        valid_hash = "not_the_right_one"
        with patch("sunny.auth._get_admin_hash", return_value=valid_hash):
            resp = client.post("/login", json={"password_hash": "wrong"})
            assert resp.status_code == 401

    def test_login_returns_session_cookie(self, client):
        """Login success sets a session cookie with HttpOnly and SameSite=Strict."""
        with patch("sunny.auth._get_admin_hash", return_value=""):
            resp = client.post("/login", json={"password": "test"})
            assert resp.status_code == 200
            set_cookie = resp.headers.get("set-cookie", "")
            assert "HttpOnly" in set_cookie
            assert "samesite=strict" in set_cookie.lower()

    def test_login_rejects_empty_credentials(self, client):
        """Login with no password or password_hash returns 400."""
        resp = client.post("/login", json={})
        assert resp.status_code == 400


class TestLogout:
    def test_logout_clears_cookie(self, client):
        resp = client.post("/logout")
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "")
        assert "Max-Age=0" in set_cookie


class TestAuthStatus:
    def test_unauthenticated_returns_false(self, client):
        resp = client.get("/auth/status")
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is False


class TestRateLimit:
    @pytest.fixture(autouse=True)
    def _reset_rate_limiter(self):
        """Reset rate limiter state before each test."""
        import sunny.auth
        sunny.auth._login_attempts.clear()
        yield
        sunny.auth._login_attempts.clear()

    def test_rate_limits_after_max_attempts(self):
        """After 5 failed attempts from same IP, login should be rate-limited."""
        with patch("sunny.auth._get_admin_hash", return_value="real_hash"):
            for i in range(5):
                resp = TestClient(create_app()).post(
                    "/login", json={"password_hash": "bad"}
                )
                # First 4 should succeed (401), 5th may trigger rate limit
                if i < 4:
                    assert resp.status_code == 401, f"Attempt {i} should be 401, got {resp.status_code}"
                else:
                    # 5th attempt may be 401 or 429 depending on exact count
                    assert resp.status_code in (401, 429)

            # 6th attempt should be rate limited
            resp = TestClient(create_app()).post(
                "/login", json={"password_hash": "bad"}
            )
            assert resp.status_code == 429
            assert "Too many" in resp.json()["detail"]
