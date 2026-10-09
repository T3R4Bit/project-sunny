"""Tests for P1 — Vault, projects, sessions.

Acceptance check:
✓ Create project → session → append turns → move session → all reflected
  on disk and in git; external edit to context.md is preserved.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from sunny.main import create_app
from sunny.projects.models import Project, ProjectCreate, Session, SessionClose, TurnAppend
from sunny.projects import service as svc
from sunny.vault.io import file_hash, read_file
from sunny.vault.git_ops import get_head_commit


@pytest.fixture()
def vault(tmp_path: Path):
    """Provide a temporary vault directory."""
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)
    yield vault


@pytest.fixture()
def client(vault):
    """Test client with vault path pointing to tmp_path."""
    with patch("sunny.projects.service._vault", return_value=vault):
        with patch("sunny.config.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.vault_path = vault
            yield TestClient(create_app())


class TestProjectCRUD:
    @pytest.fixture(autouse=True)
    def _mock_vault(self, vault):
        with patch("sunny.projects.service._vault", return_value=vault):
            yield

    def test_create_project(self, vault):
        data = ProjectCreate(slug="test-project", title="Test Project")
        p = svc.create_project(data)
        assert p.slug == "test-project"
        assert p.title == "Test Project"
        assert p.status == "active"

        # Check disk
        pf = vault / "projects" / "test-project" / "project.md"
        assert pf.exists()
        content = read_file(pf)
        assert "slug: test-project" in content

        # Check git
        head = get_head_commit(vault)
        assert head is not None

    def test_create_project_creates_context(self, vault):
        svc.create_project(ProjectCreate(slug="proj", title="Proj"))
        cf = vault / "projects" / "proj" / "context.md"
        assert cf.exists()
        content = read_file(cf)
        # Check marker sections exist
        assert "<!-- sunny:begin section=state -->" in content
        assert "<!-- sunny:begin section=decisions -->" in content

    def test_create_project_creates_sessions_dir(self, vault):
        svc.create_project(ProjectCreate(slug="proj", title="Proj"))
        sd = vault / "projects" / "proj" / "sessions"
        assert sd.is_dir()

    def test_create_duplicate_project_fails(self, vault):
        svc.create_project(ProjectCreate(slug="dup", title="Dup"))
        with pytest.raises(ValueError, match="already exists"):
            svc.create_project(ProjectCreate(slug="dup", title="Dup 2"))

    def test_get_project(self, vault):
        svc.create_project(ProjectCreate(slug="gettest", title="GetTest"))
        p = svc.get_project("gettest")
        assert p is not None
        assert p.slug == "gettest"
        assert p.title == "GetTest"

    def test_get_nonexistent_project(self, vault):
        assert svc.get_project("nope") is None

    def test_list_projects(self, vault):
        svc.create_project(ProjectCreate(slug="a", title="A"))
        svc.create_project(ProjectCreate(slug="b", title="B"))
        projects = svc.list_projects()
        assert len(projects) == 2
        slugs = {p.slug for p in projects}
        assert "a" in slugs
        assert "b" in slugs

    def test_update_project(self, vault):
        svc.create_project(ProjectCreate(slug="up", title="Original"))
        p = svc.update_project("up", svc.ProjectUpdate(title="Updated"))
        assert p is not None
        assert p.title == "Updated"
        assert get_project_on_disk(vault, "up").title == "Updated"

    def test_delete_project(self, vault):
        svc.create_project(ProjectCreate(slug="del", title="Del"))
        assert svc.delete_project("del") is True
        assert svc.get_project("del") is None

    def test_archive_project(self, vault):
        svc.create_project(ProjectCreate(slug="arch", title="Arch"))
        assert svc.archive_project("arch") is True
        p = svc.get_project("arch")
        assert p.status == "archived"

    def test_context_update(self, vault):
        svc.create_project(ProjectCreate(slug="ctx", title="Ctx"))
        ok = svc.update_context_section("ctx", "state", "Working on things")
        assert ok is True

        cf = vault / "projects" / "ctx" / "context.md"
        content = read_file(cf)
        assert "Working on things" in content

    def test_context_update_skips_on_external_edit(self, vault):
        svc.create_project(ProjectCreate(slug="ext", title="Ext"))
        cf = vault / "projects" / "ext" / "context.md"
        existing = read_file(cf)
        cf.write_text(existing + "\n\nKeaton changed this!\n")
        external_hash = file_hash(cf)

        ok = svc.merge_shared_file(
            read_file(cf) or "",
            "state",
            "new state",
            last_hash="old_hash",
            current_hash=external_hash,
        )
        merged, modified = ok
        assert modified is False


def get_project_on_disk(vault: Path, slug: str) -> Project:
    """Helper to reload a project from disk."""
    return svc.get_project(slug)


class TestSessionCRUD:
    @pytest.fixture(autouse=True)
    def _mock_vault(self, vault):
        with patch("sunny.projects.service._vault", return_value=vault):
            yield

    def test_create_session_in_project(self, vault):
        proj = svc.create_project(ProjectCreate(slug="sess-proj", title="Session Proj"))
        s = svc.create_session("Test Session", project_slug="sess-proj")
        assert s.project_slug == "sess-proj"
        assert s.status == "live"

        # Check disk
        sd = vault / "projects" / "sess-proj" / "sessions"
        assert any(sd.glob("*.md"))

    def test_create_home_session(self, vault):
        s = svc.create_session("Home Chat", project_slug=None)
        assert s.project_slug is None
        assert s.status == "live"

        # Check disk in chats/
        cd = vault / "chats"
        assert cd.exists()
        assert any(cd.glob("*.md"))

    def test_append_turn(self, vault):
        proj = svc.create_project(ProjectCreate(slug="turn-proj", title="Turn Proj"))
        s = svc.create_session("Turn Session", project_slug="turn-proj")

        svc.append_turn(s, TurnAppend(role="Keaton", content="Hello"))
        svc.append_turn(s, TurnAppend(role="Sunny", content="Hi there"))

        # Check disk content
        sd = vault / "projects" / "turn-proj" / "sessions"
        md_files = list(sd.glob("*.md"))
        assert len(md_files) >= 1
        content = read_file(md_files[0])
        assert "### Keaton" in content
        assert "Hello" in content
        assert "### Sunny" in content

    def test_close_session(self, vault):
        proj = svc.create_project(ProjectCreate(slug="close-proj", title="Close Proj"))
        s = svc.create_session("Close Session", project_slug="close-proj")
        assert s.status == "live"

        close_data = SessionClose(
            summary="A brief summary of the session",
            topics=["topic1", "topic2"],
            decisions=["decision1"],
            open_questions=["q1"],
        )
        s = svc.close_session(s, close_data)
        assert s.status == "closed"
        assert s.summary == "A brief summary of the session"

    def test_move_session(self, vault):
        proj_a = svc.create_project(ProjectCreate(slug="move-a", title="Move A"))
        proj_b = svc.create_project(ProjectCreate(slug="move-b", title="Move B"))

        s = svc.create_session("Move Session", project_slug="move-a")
        moved = svc.move_session(s, "move-b")
        assert moved.project_slug == "move-b"

        # Check disk: file should be in move-b/sessions, not move-a
        dir_b = vault / "projects" / "move-b" / "sessions"
        dir_a = vault / "projects" / "move-a" / "sessions"
        assert list(dir_b.glob("*.md"))
        assert not list(dir_a.glob("*move*"))

    def test_move_session_to_home(self, vault):
        proj = svc.create_project(ProjectCreate(slug="tohome", title="ToHome"))
        s = svc.create_session("Home Bound", project_slug="tohome")
        moved = svc.move_session(s, None)
        assert moved.project_slug is None

    def test_session_reflects_on_disk(self, vault):
        """Full pipeline: create project → session → append turns → move → on disk."""
        proj = svc.create_project(ProjectCreate(slug="disk", title="Disk Test"))
        s = svc.create_session("Disk Session", project_slug="disk")
        svc.append_turn(s, TurnAppend(role="Keaton", content="Question"))
        svc.append_turn(s, TurnAppend(role="Sunny", content="Answer"))
        moved = svc.move_session(s, None)

        # Session file exists in home chats
        cd = vault / "chats"
        session_files = list(cd.glob("*.md"))
        assert len(session_files) >= 1

        content = read_file(session_files[0])
        assert "### Keaton" in content
        assert "Question" in content

    def test_close_session_updates_project_context(self, vault):
        proj = svc.create_project(ProjectCreate(slug="ctx-close", title="Ctx Close"))
        s = svc.create_session("Context Session", project_slug="ctx-close")

        close_data = SessionClose(
            summary="Session summary",
            decisions=["Fixed the build"],
            open_questions=["Should we refactor?"],
        )
        svc.close_session(s, close_data)

        cf = vault / "projects" / "ctx-close" / "context.md"
        content = read_file(cf)
        assert "Fixed the build" in content
        assert "Should we refactor?" in content


class TestExternalEditPreservation:
    @pytest.fixture(autouse=True)
    def _mock_vault(self, vault):
        with patch("sunny.projects.service._vault", return_value=vault):
            yield

    def test_external_edit_to_context_preserved(self, vault):
        """External edits to context.md must be preserved (byte-for-byte for non-marker regions)."""
        proj = svc.create_project(ProjectCreate(slug="preserve", title="Preserve"))
        cf = vault / "projects" / "preserve" / "context.md"

        # Simulate external edit
        original = read_file(cf)
        cf.write_text(original + "\n\nKeaton's personal note\n")

        # Now try to update a section — it should detect external change
        merged, modified = svc.merge_shared_file(
            read_file(cf) or "",
            "state",
            "new state",
            last_hash="old_hash",  # different from current
            current_hash="new_hash",
        )
        assert modified is False
        # Original content should still be there
        assert "Keaton's personal note" in merged

    def test_sync_conflict_detection(self, vault):
        """Sync conflict files are detected and tracked."""
        from sunny.watcher import record_sync_conflict, get_sync_conflicts

        record_sync_conflict("projects/test/file.md.sync-conflict-20261001")
        conflicts = get_sync_conflicts()
        assert len(conflicts) >= 1
        assert "file.md.sync-conflict-20261001" in conflicts[-1]["path"]


class TestAPI:
    def test_create_project_via_api(self, client, vault):
        resp = client.post("/projects", json={"slug": "api-proj", "title": "API Project"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "api-proj"
        assert data["title"] == "API Project"

    def test_list_projects_via_api(self, client, vault):
        client.post("/projects", json={"slug": "list-proj", "title": "List Project"})
        resp = client.get("/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["slug"] == "list-proj"

    def test_get_session_via_api(self, client, vault):
        client.post("/projects", json={"slug": "get-s-proj", "title": "Get S Proj"})
        client.post("/projects/get-s-proj/sessions", json={"title": "S1", "kind": "chat"})
        resp = client.get("/projects/get-s-proj/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_append_turn_via_api(self, client, vault):
        client.post("/projects", json={"slug": "turn-api-proj", "title": "Turn API"})
        resp = client.post("/projects/turn-api-proj/sessions", json={"title": "API Session"})
        slug = resp.json()["slug"]
        resp = client.post(
            f"/projects/turn-api-proj/sessions/{slug}/append",
            json={"role": "Keaton", "content": "Test message"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_close_session_via_api(self, client, vault):
        client.post("/projects", json={"slug": "close-api-proj", "title": "Close API"})
        resp = client.post("/projects/close-api-proj/sessions", json={"title": "To Close"})
        slug = resp.json()["slug"]
        resp = client.post(
            f"/projects/close-api-proj/sessions/{slug}/close",
            json={"summary": "Done", "decisions": ["d1"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "closed"
        assert data["summary"] == "Done"

    def test_move_session_via_api(self, client, vault):
        client.post("/projects", json={"slug": "move-api-a", "title": "Move A"})
        client.post("/projects", json={"slug": "move-api-b", "title": "Move B"})
        resp = client.post("/projects/move-api-a/sessions", json={"title": "Moving"})
        slug = resp.json()["slug"]
        resp = client.post(
            f"/projects/move-api-a/sessions/{slug}/move",
            json={"new_project": "move-api-b"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_slug"] == "move-api-b"

    def test_create_duplicate_project_returns_409(self, client):
        client.post("/projects", json={"slug": "conflict", "title": "First"})
        resp = client.post("/projects", json={"slug": "conflict", "title": "Second"})
        assert resp.status_code == 409

    def test_get_nonexistent_project_returns_404(self, client):
        resp = client.get("/projects/nope")
        assert resp.status_code == 404

    def test_home_session(self, client, vault):
        resp = client.post("/chats/sessions", json={"title": "Home Chat"})
        assert resp.status_code == 200
        assert resp.json()["project_slug"] is None

    def test_home_append_turn(self, client, vault):
        resp = client.post("/chats/sessions", json={"title": "Home Chat"})
        assert resp.status_code == 200
        slug = resp.json()["slug"]
        resp = client.post(
            f"/chats/sessions/{slug}/append",
            json={"role": "Keaton", "content": "Hello"},
        )
        assert resp.status_code == 200

    def test_home_close_session(self, client, vault):
        resp = client.post("/chats/sessions", json={"title": "Home Chat"})
        assert resp.status_code == 200
        slug = resp.json()["slug"]
        resp = client.post(
            f"/chats/sessions/{slug}/close",
            json={"summary": "Finished"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"


class TestWatchSyncConflictsAPI:
    def test_list_sync_conflicts(self, client):
        from sunny.watcher import record_sync_conflict, get_sync_conflicts

        record_sync_conflict("test.conflict")
        resp = client.get("/sync/conflicts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_clear_sync_conflicts(self, client):
        from sunny.watcher import record_sync_conflict

        record_sync_conflict("to-clear")
        resp = client.post("/sync/conflicts/clear")
        assert resp.status_code == 200
        resp = client.get("/sync/conflicts")
        assert len(resp.json()) == 0
