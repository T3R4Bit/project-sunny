"""Research router — API for research sessions and source ingest."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from sunny.extraction.extractors import get_extractor
from sunny.research.service import (
    add_source_to_research,
    create_research_session,
    generate_report,
    get_research_session,
    list_research_sessions,
    list_research_sources,
)

router = APIRouter(tags=["research"])


@router.get("/research")
def list_research() -> list[dict]:
    """List all research sessions."""
    return list_research_sessions()


@router.get("/research/{slug}")
def get_research(slug: str) -> dict:
    """Get a research session."""
    session = get_research_session(slug)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")
    return session.model_dump()


@router.post("/research")
def create_research(body: dict) -> dict:
    """Create a new research session."""
    title = body.get("title", "Untitled Research")
    goal = body.get("goal", "")
    project_slug = body.get("project_slug")
    try:
        return create_research_session(title=title, goal=goal, project_slug=project_slug)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/research/{slug}/sources")
def list_sources(slug: str) -> list[dict]:
    """List sources in a research session."""
    return list_research_sources(slug)


@router.post("/research/{slug}/sources")
def ingest_source(slug: str, body: dict) -> dict:
    """Ingest a source into a research session."""
    from sunny.research.models import SourceIngest
    kind = body.get("kind", "text")
    content = body.get("content", "")
    url = body.get("url")
    filename = body.get("filename")
    file_data = body.get("file_data")

    extractor = get_extractor(kind)
    if not extractor:
        raise HTTPException(status_code=400, detail=f"No extractor for kind: {kind}")

    try:
        ingest = SourceIngest(kind=kind, content=content, url=url, filename=filename, file_data=file_data)
        result = add_source_to_research(slug, ingest)
        return result.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/research/{slug}/report")
def research_report(slug: str) -> dict:
    """Generate report for a research session."""
    try:
        report = generate_report(slug)
        return {"report": report}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/research/{slug}/citations")
def research_citations(slug: str) -> dict:
    """Get research session with citation-ready source context."""
    session = get_research_session(slug)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")
    from sunny.research.service import _build_citation_context
    context = _build_citation_context(session)
    return {
        "sources_context": context,
        "source_count": len(session.sources),
    }
