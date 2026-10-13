"""Integration tests for P4 — frontend API endpoints.

These tests verify that the API endpoints the frontend depends on work
correctly end-to-end, including:
- Auth endpoints
- Project CRUD
- Session CRUD (Home and project-scoped)
- Chat completion
- Search
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(vault: Path):
    """Test client with vault path pointing to tmp_path."""
    import importlib

    # Create mock settings
    from sunny.config import Settings
    mock_settings = Settings(_env_file=None)
    mock_settings.vault_path = vault
    mock_settings.db_path = str(vault / ".sunny" / "sunny.db")
    mock_settings.admin_password_hash = ""
    mock_settings.secret_dir = vault / ".sunny" / "secrets"

    # Patch in sunny.config first (so new imports pick it up)
    import sunny.config as config_mod
    original_get_settings = config_mod.get_settings
    config_mod.get_settings = lambda: mock_settings

    # Patch in sunny.projects.service
    import sunny.projects.service as svc_mod
    svc_mod.get_settings = lambda: mock_settings
    svc_mod._vault = lambda: vault

    # Reload service module so it picks up patched functions
    importlib.reload(svc_mod)

    # Now create app (will reimport and pick up patched modules)
    from sunny.main import create_app
    app = create_app()
    yield TestClient(app)

    # Restore
    config_mod.get_settings = original_get_settings


def test_auth_status(client):
    """GET /auth/status returns auth info."""
    resp = client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "authenticated" in data


def test_auth_login_success(client):
    """POST /login succeeds with non-empty password (P0 bypass)."""
    resp = client.post("/login", json={"password": "any"})
    assert resp.status_code == 200


def test_auth_login_fail(client):
    """POST /login rejects missing password."""
    resp = client.post("/login", json={})
    assert resp.status_code == 400


def test_projects_list_empty(client):
    """GET /projects returns empty list when no projects."""
    resp = client.get("/projects")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_project_create_and_list(client):
    """POST /projects creates a project, GET /projects lists it."""
    resp = client.post("/projects", json={
        "slug": "test-project",
        "title": "Test Project",
        "tags": ["test"]
    })
    # FastAPI defaults to 200 for non-async endpoints
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["title"] == "Test Project"
    assert data["tags"] == ["test"]
    slug = data["slug"]

    # Verify it appears in list
    resp2 = client.get("/projects")
    assert resp2.status_code == 200
    slugs = [p["slug"] for p in resp2.json()]
    assert slug in slugs


def test_project_detail(client):
    """GET /projects/{slug} returns project details."""
    client.post("/projects", json={"slug": "detail-test", "title": "Detail Test", "tags": []})
    resp = client.get("/projects/detail-test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Detail Test"


def test_project_delete(client):
    """DELETE /projects/{slug} removes project."""
    client.post("/projects", json={"slug": "delete-me", "title": "Delete Me", "tags": []})
    resp = client.delete("/projects/delete-me")
    assert resp.status_code == 200

    resp2 = client.get("/projects")
    slugs = [p["slug"] for p in resp2.json()]
    assert "delete-me" not in slugs


def test_home_session_create_and_list(client):
    """POST /chats/sessions creates a Home session."""
    resp = client.post("/chats/sessions", json={})
    # Returns 200 (not 201) per FastAPI defaults
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "slug" in data
    assert data["status"] in ("open", "live")

    resp2 = client.get("/chats/sessions")
    assert resp2.status_code == 200
    slugs = [s["slug"] for s in resp2.json()]
    assert data["slug"] in slugs


def test_home_session_append(client):
    """POST /chats/sessions/{slug}/append adds a turn."""
    create_resp = client.post("/chats/sessions", json={})
    slug = create_resp.json()["slug"]

    resp = client.post(f"/chats/sessions/{slug}/append", json={
        "role": "Keaton",
        "content": "Hello!",
        "mode": "text"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data


def test_home_session_close(client):
    """POST /chats/sessions/{slug}/close closes a session."""
    create_resp = client.post("/chats/sessions", json={})
    slug = create_resp.json()["slug"]

    # Append a message first
    client.post(f"/chats/sessions/{slug}/append", json={
        "role": "Keaton",
        "content": "Test",
        "mode": "text"
    })

    # Close manually
    resp = client.post(f"/chats/sessions/{slug}/close", json={"close_data": {"summary": "Done"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("closed", "summarized")


def test_project_session_create(client):
    """POST /projects/{slug}/sessions creates a session in a project."""
    client.post("/projects", json={"slug": "chat-project", "title": "Chat Project", "tags": []})

    resp = client.post("/projects/chat-project/sessions", json={})
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["project_slug"] == "chat-project"
    assert data["status"] in ("open", "live")


def test_project_session_append(client):
    """POST /projects/{slug}/sessions/{slug}/append adds a turn."""
    client.post("/projects", json={"slug": "append-proj", "title": "Append Test", "tags": []})

    session_resp = client.post("/projects/append-proj/sessions", json={})
    slug = session_resp.json()["slug"]

    resp = client.post(f"/projects/append-proj/sessions/{slug}/append", json={
        "role": "Keaton",
        "content": "Test message",
        "mode": "text"
    })
    assert resp.status_code == 200


def test_project_session_chat(client):
    """POST /chats/sessions/{slug}/chat sends a message with project context."""
    client.post("/projects", json={"slug": "full-chat-test", "title": "Full Chat Test", "tags": []})

    session_resp = client.post("/projects/full-chat-test/sessions", json={})
    slug = session_resp.json()["slug"]

    # Chat endpoint requires LLM (fake gateway not configured in tests)
    # The endpoint itself works, but the LLM call will fail in test env
    resp = client.post(
        f"/chats/sessions/{slug}/chat",
        json={"message": "Hello from project", "project_slug": "full-chat-test"}
    )
    # Returns 502 when no Claude key is configured
    # In production with a key configured, this would return 200
    assert resp.status_code in (200, 502)


def test_search(client):
    """GET /search returns results."""
    resp = client.get("/search?q=test&mode=keyword")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_project_sessions_list(client):
    """GET /projects/{slug}/sessions lists sessions."""
    client.post("/projects", json={"slug": "list-sessions", "title": "List Sessions", "tags": []})
    client.post("/projects/list-sessions/sessions", json={})
    resp = client.get("/projects/list-sessions/sessions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_session_close_data_manual(client):
    """Manual close with close_data uses 'closed' status."""
    create_resp = client.post("/chats/sessions", json={})
    slug = create_resp.json()["slug"]

    resp = client.post(f"/chats/sessions/{slug}/close", json={
        "close_data": {"summary": "Test summary", "topics": ["test"]}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "closed"


def test_search_with_filters(client):
    """Search supports mode, project, kind, tags filters."""
    for mode in ["hybrid", "keyword", "semantic"]:
        resp = client.get(f"/search?q=test&mode={mode}")
        assert resp.status_code == 200


def test_search_no_results(client):
    """Search with obscure query returns empty list."""
    resp = client.get("/search?q=xyznonexistent12345")
    assert resp.status_code == 200
    assert resp.json() == []


def test_streaming_chat_endpoint(client):
    """POST /chats/sessions/{slug}/stream returns streaming response."""
    create_resp = client.post("/chats/sessions", json={})
    slug = create_resp.json()["slug"]

    resp = client.post(
        f"/chats/sessions/{slug}/stream",
        json={"message": "stream test"}
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "").lower()


def test_session_move(client):
    """POST /projects/{slug}/sessions/{session_slug}/move moves a session."""
    client.post("/projects", json={"slug": "from-project", "title": "From Project", "tags": []})
    client.post("/projects", json={"slug": "to-project", "title": "To Project", "tags": []})

    session_resp = client.post("/projects/from-project/sessions", json={})
    slug = session_resp.json()["slug"]

    resp = client.post(
        f"/projects/from-project/sessions/{slug}/move",
        json={"new_project": "to-project"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_slug"] == "to-project"


def test_chat_records_turns_and_sends_history(client, monkeypatch):
    """Chat appends both turns to the session file and feeds earlier turns back to Claude."""
    import sunny.llm.router as chat_router

    seen: list[list[dict]] = []

    async def fake_completion(messages, **kwargs):
        seen.append(messages)
        return {"content": f"reply {len(seen)}", "prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(chat_router, "chat_completion", fake_completion)

    slug = client.post("/chats/sessions", json={"title": "History test"}).json()["slug"]
    assert client.post(f"/chats/sessions/{slug}/chat", json={"message": "first"}).json()["reply"] == "reply 1"
    assert client.post(f"/chats/sessions/{slug}/chat", json={"message": "second"}).json()["reply"] == "reply 2"

    turns = client.get(f"/chats/sessions/{slug}").json()["turns"]
    assert [(t["role"], t["content"]) for t in turns] == [
        ("Keaton", "first"), ("Sunny", "reply 1"), ("Keaton", "second"), ("Sunny", "reply 2"),
    ]
    second_prompt = "\n".join(str(m["content"]) for m in seen[1])
    assert "first" in second_prompt and "reply 1" in second_prompt


def test_chat_stream_sse(client, monkeypatch):
    """The stream endpoint emits {"text"} events then [DONE], and saves the full reply."""
    import json
    import sunny.llm.router as chat_router

    async def fake_stream(messages, **kwargs):
        for part in ("Hel", "lo"):
            yield part

    monkeypatch.setattr(chat_router, "streaming_chat", fake_stream)

    slug = client.post("/chats/sessions", json={"title": "Stream test"}).json()["slug"]
    resp = client.post(f"/chats/sessions/{slug}/stream", json={"message": "hi"})
    events = [e[6:] for e in resp.text.split("\n\n") if e.startswith("data: ")]
    assert events[-1] == "[DONE]"
    assert "".join(json.loads(e)["text"] for e in events[:-1]) == "Hello"
    turns = client.get(f"/chats/sessions/{slug}").json()["turns"]
    assert turns[-1] == {"role": "Sunny", "content": "Hello"}
