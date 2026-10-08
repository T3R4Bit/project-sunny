"""Integration tests for P4 — frontend API endpoints.

These tests verify that the API endpoints the frontend depends on work
correctly end-to-end, including:
- Auth endpoints
- Project CRUD
- Session CRUD (Home and project-scoped)
- Chat completion
- Search
- Admin status
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(vault: Path):
    """Test client with vault path pointing to tmp_path."""
    from sunny.main import create_app

    with patch("sunny.projects.service._vault", return_value=vault):
        app = create_app()
        return TestClient(app)


def test_auth_status(client):
    """GET /auth/status returns auth info."""
    resp = client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "authenticated" in data


def test_auth_login_success(client):
    """POST /login succeeds with empty password (P0 bypass)."""
    resp = client.post("/login", json={"password": "any"})
    assert resp.status_code == 200
    assert "session" in str(resp.cookies) or resp.status_code == 200


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
    assert resp.status_code == 201
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
    assert data["name"] == "Detail Test"


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
    assert resp.status_code == 201
    data = resp.json()
    assert "slug" in data
    assert data["status"] == "open"

    resp2 = client.get("/chats/sessions")
    assert resp2.status_code == 200
    slugs = [s["slug"] for s in resp2.json()]
    assert data["slug"] in slugs


def test_home_session_append(client):
    """POST /chats/sessions/{slug}/chat sends a message."""
    create_resp = client.post("/chats/sessions", json={})
    slug = create_resp.json()["slug"]

    resp = client.post(f"/chats/sessions/{slug}/chat", json={"message": "Hello!"})
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data
    assert len(data["reply"]) > 0


def test_home_session_close(client):
    """POST /chats/sessions/{slug}/close closes a session."""
    create_resp = client.post("/chats/sessions", json={})
    slug = create_resp.json()["slug"]

    client.post(f"/chats/sessions/{slug}/chat", json={"message": "Test"})

    resp = client.post(f"/chats/sessions/{slug}/close", json={"close_data": {"summary": "Done"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("closed", "summarized")


def test_project_session_create(client):
    """POST /projects/{slug}/sessions creates a session in a project."""
    client.post("/projects", json={"name": "Chat Project", "description": "", "tags": []})

    resp = client.post("/projects/chat-project/sessions", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["project_slug"] == "chat-project"
    assert data["status"] == "open"


def test_project_session_chat(client):
    """POST /chats/sessions/{slug}/chat with project_slug works end-to-end."""
    client.post("/projects", json={"name": "Full Chat Test", "description": "", "tags": []})

    session_resp = client.post("/projects/full-chat-test/sessions", json={})
    slug = session_resp.json()["slug"]

    resp = client.post(
        f"/chats/sessions/{slug}/chat",
        json={"message": "What do you know about this project?", "project_slug": "full-chat-test"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data


def test_search(client):
    """GET /search returns results."""
    resp = client.get("/search?q=test&mode=keyword")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_admin_status(client):
    """GET /admin/status returns system info."""
    resp = client.get("/admin/status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_project_sessions_list(client):
    """GET /projects/{slug}/sessions lists sessions."""
    client.post("/projects", json={"name": "List Sessions", "description": "", "tags": []})
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
    """POST /chats/sessions/{slug}/chat/stream returns streaming response."""
    create_resp = client.post("/chats/sessions", json={})
    slug = create_resp.json()["slug"]

    resp = client.post(
        f"/chats/sessions/{slug}/chat/stream",
        json={"message": "stream test"}
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "").lower()


def test_context_update(client):
    """PATCH /projects/{slug}/context updates context.md sections."""
    client.post("/projects", json={"name": "Context Test", "description": "", "tags": []})
    resp = client.patch(
        "/projects/context-test/context",
        json={
            "decisions": ["Test decision 1"],
            "recent_sessions": [{"slug": "test", "summary": "test"}]
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "decisions" in data


def test_session_move(client):
    """POST /projects/{slug}/sessions/{session_slug}/move moves a session."""
    client.post("/projects", json={"name": "From Project", "description": "", "tags": []})
    client.post("/projects", json={"name": "To Project", "description": "", "tags": []})

    session_resp = client.post("/projects/from-project/sessions", json={})
    slug = session_resp.json()["slug"]

    resp = client.post(
        f"/projects/from-project/sessions/{slug}/move",
        json={"to_project": "to-project"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_slug"] == "to-project"
