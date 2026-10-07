"""Health endpoint test — verifies the /health route."""

import pytest
from fastapi.testclient import TestClient

from sunny.main import create_app


@pytest.fixture()
def app() -> TestClient:
    return TestClient(create_app())


class TestHealth:
    def test_health_returns_ok(self, app: TestClient) -> None:
        resp = app.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "vault_path" in data
        assert "db_path" in data

    def test_health_is_json(self, app: TestClient) -> None:
        resp = app.get("/health")
        assert resp.headers["content-type"] == "application/json"
