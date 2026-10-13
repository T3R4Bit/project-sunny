"""Daily brief and integrations: degrade gracefully, store results, gate OAuth by state."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import sunny.config as config_mod
from sunny.config import Settings


@pytest.fixture
def settings(tmp_path: Path, monkeypatch):
    s = Settings(_env_file=None)
    s.vault_path = tmp_path / "vault"
    s.db_path = tmp_path / "state" / "sunny.db"
    s.secret_dir = tmp_path / "state" / "secrets"
    s.vault_path.mkdir(parents=True)
    monkeypatch.setattr(config_mod, "get_settings", lambda: s)
    return s


@pytest.fixture
def client(settings):
    from sunny.main import create_app
    return TestClient(create_app(), base_url="https://testserver")


def test_brief_with_nothing_configured(settings, monkeypatch):
    from sunny import brief

    monkeypatch.setattr(brief, "_write_up", lambda label, sections: "Quiet day.")
    monkeypatch.setattr("sunny.projects.service._vault", lambda: settings.vault_path)
    b = brief.generate()
    assert b["summary"] == "Quiet day."
    for key in ("weather", "calendar", "email", "health"):
        assert b["sections"][key]["status"] == "unconfigured"
    assert b["sections"]["vault"]["status"] == "ok"
    assert brief.load()["summary"] == "Quiet day."
    assert (settings.vault_path / "briefs" / f"{b['date']}.md").exists()


def test_failing_source_becomes_a_note(settings, monkeypatch):
    from sunny import brief, integrations

    settings.openweathermap_api_key = "k"
    settings.weather_locations = "Nowhere,XX"

    def boom(_loc):
        raise RuntimeError("weather down")

    monkeypatch.setattr(integrations, "weather_for", boom)
    monkeypatch.setattr(brief, "_write_up", lambda label, sections: "ok")
    b = brief.generate(save=False)
    assert b["sections"]["weather"]["status"] == "error"
    assert "weather down" in b["sections"]["weather"]["note"]


def test_brief_endpoints(client, monkeypatch):
    from sunny import brief

    assert client.get("/brief").json()["summary"] is None
    monkeypatch.setattr(brief, "gather", lambda: {k: {"status": "unconfigured", "note": ""}
                                                  for k in ("weather", "calendar", "email", "health", "vault")})
    monkeypatch.setattr(brief, "_write_up", lambda label, sections: "Hello Keaton.")
    assert client.post("/brief/refresh").json()["summary"] == "Hello Keaton."
    got = client.get("/brief").json()
    assert got["summary"] == "Hello Keaton." and got["stale"] is False


def test_integrations_list_and_unconfigured_checks(client):
    rows = {r["key"]: r for r in client.get("/integrations").json()}
    assert set(rows) == {"claude", "weather", "google", "garmin"}
    assert rows["google"]["configured"] is False
    res = client.post("/integrations/weather/check").json()
    assert res["ok"] is False and "OPENWEATHERMAP_API_KEY" in res["detail"]
    assert client.post("/integrations/nope/check").status_code == 404


def test_google_callback_rejects_unknown_state(client, settings):
    settings.public_url = "https://sunny.example/"
    resp = client.get("/auth/google/callback?state=forged&code=x", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].endswith("google=bad_state")


def test_google_start_requires_config(client, settings):
    assert client.post("/integrations/google/start").status_code == 400
    settings.google_client_id, settings.google_client_secret = "id", "secret"
    settings.google_redirect_uri = "https://sunny.example:5443/auth/google/callback"
    url = client.post("/integrations/google/start").json()["url"]
    assert url.startswith("https://accounts.google.com/") and "access_type=offline" in url
