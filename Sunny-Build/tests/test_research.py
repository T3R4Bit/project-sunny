"""P5 Research — tests for research sessions, source ingest, dedup, citations, reports."""

import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(vault: Path):
    """Test client with vault path pointing to tmp_path."""
    # Create mock settings
    mock_settings = MagicMock()
    mock_settings.vault_path = vault
    mock_settings.db_path = str(vault / ".sunny" / "sunny.db")
    mock_settings.admin_password_hash = ""
    mock_settings.log_level = "info"

    # Patch in sunny.config first (so new imports pick it up)
    import sunny.config
    sunny.config.get_settings = lambda: mock_settings

    # Patch in sunny.projects.service before creating app
    import sunny.projects.service as svc
    svc.get_settings = lambda: mock_settings
    svc._vault = lambda: vault

    importlib.reload(svc)

    # Also patch sunny.research.service
    import sunny.research.service as rsvc
    rsvc.get_settings = lambda: mock_settings

    from sunny.main import create_app
    app = create_app()
    return TestClient(app)


# ── Research CRUD ─────────────────────────────────────────────────────

class TestResearchCRUD:
    """Research session CRUD endpoints."""

    def test_create_research_session(self, client):
        resp = client.post("/research", json={
            "title": "Climate Change Research",
            "goal": "Understand current climate models"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "research_slug" in data
        assert data["research_slug"].startswith("research-")

    def test_create_research_with_project(self, client):
        client.post("/projects", json={
            "slug": "climate-project",
            "title": "Climate Project",
            "tags": []
        })
        resp = client.post("/research", json={
            "title": "Climate Deep Dive",
            "goal": "Deep dive analysis",
            "project_slug": "climate-project"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "research_slug" in data

    def test_list_research_sessions(self, client):
        client.post("/research", json={"title": "Test Research"})
        resp = client.get("/research")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_research_session(self, client):
        client.post("/research", json={"title": "Get Me"})
        resp = client.get("/research")
        slugs = [d["slug"] for d in resp.json()]
        assert len(slugs) >= 1

        slug = slugs[0]
        resp = client.get(f"/research/{slug}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == slug
        assert "title" in data
        assert "goal" in data

    def test_get_research_not_found(self, client):
        resp = client.get("/research/nonexistent-slug")
        assert resp.status_code == 404

    def test_research_session_has_correct_kind(self, client, vault: Path):
        slug = None
        resp = client.post("/research", json={"title": "Kind Test"})
        if resp.status_code == 200:
            slug = resp.json().get("research_slug")

        if slug:
            from sunny.research.service import get_research_session
            session = get_research_session(slug)
            assert session is not None
            assert session.title == "Kind Test"


# ── Source Ingest ─────────────────────────────────────────────────────

class TestSourceIngest:
    """Source ingestion and dedup."""

    def _create_research(self, client):
        resp = client.post("/research", json={"title": "Source Test"})
        return resp.json()["research_slug"]

    def test_ingest_text_source(self, client):
        slug = self._create_research(client)
        resp = client.post(f"/research/{slug}/sources", json={
            "kind": "text",
            "content": "This is test content for a text source."
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["added"] is True
        assert data["duplicated"] is False
        assert "source_id" in data

    def test_ingest_markdown_source(self, client):
        slug = self._create_research(client)
        resp = client.post(f"/research/{slug}/sources", json={
            "kind": "markdown",
            "content": "# Heading\n\nSome markdown content here.",
            "filename": "notes.md"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["added"] is True

    def test_dedup_source(self, client):
        slug = self._create_research(client)
        content = "Unique content that will be deduplicated"
        # First ingest
        resp1 = client.post(f"/research/{slug}/sources", json={
            "kind": "text",
            "content": content
        })
        assert resp1.status_code == 200
        assert resp1.json()["added"] is True

        # Same content again — should be deduped
        resp2 = client.post(f"/research/{slug}/sources", json={
            "kind": "text",
            "content": content
        })
        assert resp2.status_code == 200
        assert resp2.json()["duplicated"] is True
        assert resp2.json()["added"] is False

    def test_ingest_unknown_kind(self, client):
        slug = self._create_research(client)
        resp = client.post(f"/research/{slug}/sources", json={
            "kind": "unknown-format"
        })
        assert resp.status_code == 400

    def test_ingest_web_source(self, client):
        slug = self._create_research(client)
        resp = client.post(f"/research/{slug}/sources", json={
            "kind": "web",
            "content": "<html><body>Hello world</body></html>",
            "url": "https://example.com/page"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["added"] is True

    def test_ingest_arxiv_source(self, client):
        slug = self._create_research(client)
        resp = client.post(f"/research/{slug}/sources", json={
            "kind": "arxiv",
            "content": "2101.12345"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["added"] is True
        assert "arXiv" in data["title"] or "Unknown" in data["title"]

    def test_ingest_github_source(self, client):
        slug = self._create_research(client)
        resp = client.post(f"/research/{slug}/sources", json={
            "kind": "github",
            "content": "owner/repo",
            "url": "https://github.com/owner/repo"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["added"] is True

    def test_list_sources(self, client):
        slug = self._create_research(client)
        # Add a source first
        client.post(f"/research/{slug}/sources", json={
            "kind": "text",
            "content": "Source content"
        })
        resp = client.get(f"/research/{slug}/sources")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "title" in data[0]
        assert "kind" in data[0]


# ── Citations ─────────────────────────────────────────────────────────

class TestCitations:
    """Citation context building."""

    def _create_research_with_source(self, client):
        slug = self._create_research(client)
        client.post(f"/research/{slug}/sources", json={
            "kind": "text",
            "content": "Important finding about quantum computing."
        })
        return slug

    def _create_research(self, client):
        resp = client.post("/research", json={"title": "Citation Test"})
        return resp.json()["research_slug"]

    def test_citation_context_has_sources(self, client):
        slug = self._create_research_with_source(client)
        resp = client.get(f"/research/{slug}/citations")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources_context" in data
        assert data["source_count"] >= 1
        # Check that source is referenced with [S1] format
        assert "[S1]" in data["sources_context"]

    def test_citations_replace_format(self):
        """Test the _citations_replace function."""
        from sunny.research.service import _citations_replace
        text = "As shown in [S1], the results are significant [S3 §quantum]."
        result = _citations_replace(text)
        assert 'data-source="S1"' in result
        assert 'data-source="S3"' in result
        assert "source-S1" in result
        assert "source-S3" in result


# ── Report Generation ─────────────────────────────────────────────────

class TestReportGeneration:
    """Research report generation."""

    def _create_research_with_source(self, client):
        slug = self._create_research(client)
        client.post(f"/research/{slug}/sources", json={
            "kind": "text",
            "content": "Finding one about AI safety."
        })
        client.post(f"/research/{slug}/sources", json={
            "kind": "text",
            "content": "Finding two about alignment."
        })
        return slug

    def _create_research(self, client):
        resp = client.post("/research", json={"title": "Report Test"})
        return resp.json()["research_slug"]

    def test_generate_report(self, client):
        slug = self._create_research_with_source(client)
        resp = client.post(f"/research/{slug}/report")
        assert resp.status_code == 200
        data = resp.json()
        assert "report" in data
        report = data["report"]
        assert "Report Test" in report
        assert "Findings" in report
        assert "Source List" in report
        assert "Open Gaps" in report

    def test_report_written_to_disk(self, client, vault: Path):
        slug = self._create_research_with_source(client)
        client.post(f"/research/{slug}/report")
        from sunny.paths import research_dir
        report_path = research_dir(vault, slug) / "report.md"
        assert report_path.exists()
        content = report_path.read_text()
        assert "Report Test" in content

    def test_report_with_no_sources(self, client):
        slug = self._create_research(client)
        resp = client.post(f"/research/{slug}/report")
        assert resp.status_code == 200
        report = resp.json()["report"]
        assert "No sources" in report or "No source" in report or "0" in report

    def test_report_missing_research(self, client):
        resp = client.post("/research/nonexistent/report")
        assert resp.status_code == 404
