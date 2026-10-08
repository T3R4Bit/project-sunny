"""Projects — FastAPI routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from sunny.projects.models import ProjectUpdate, SessionClose, TurnAppend
from sunny.projects import service as svc

router = APIRouter(tags=["projects"])


# ── Projects ─────────────────────────────────────────────────────────────


@router.get("/projects")
def list_projects() -> list[dict]:
    return [p.model_dump() for p in svc.list_projects()]


@router.get("/projects/{slug}")
def get_project(slug: str) -> dict:
    p = svc.get_project(slug)
    if not p:
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")
    return p.model_dump()


@router.post("/projects")
def create_project(data: svc.ProjectCreate) -> dict:
    try:
        p = svc.create_project(data)
        return p.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.patch("/projects/{slug}")
def update_project(slug: str, data: ProjectUpdate) -> dict:
    p = svc.update_project(slug, data)
    if not p:
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")
    return p.model_dump()


@router.delete("/projects/{slug}")
def delete_project(slug: str) -> dict:
    if not svc.delete_project(slug):
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")
    return {"status": "deleted"}


@router.post("/projects/{slug}/archive")
def archive_project(slug: str) -> dict:
    if not svc.archive_project(slug):
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")
    return {"status": "archived"}


@router.get("/projects/{slug}/context")
def get_project_context(slug: str) -> str:
    from sunny.paths import context_file
    from sunny.vault.io import read_file

    p = svc.get_project(slug)
    if not p:
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")

    cf = context_file(p.slug if hasattr(p, 'slug') else slug)
    content = read_file(cf)
    return content or ""


@router.patch("/projects/{slug}/context")
def update_project_context(
    slug: str,
    sections: dict[str, str],
) -> dict:
    updated = svc.update_context_sections(slug, sections)
    return {"status": "ok", "updated_sections": updated}


# ── Sessions ─────────────────────────────────────────────────────────────


@router.get("/projects/{slug}/sessions")
def list_sessions(slug: str) -> list[dict]:
    return [s.model_dump() for s in svc.list_sessions(slug)]


@router.get("/chats/sessions")
def list_home_sessions() -> list[dict]:
    return [s.model_dump() for s in svc.list_sessions(None)]


@router.get("/projects/{slug}/sessions/{session_slug}")
def get_session(
    slug: str,
    session_slug: str,
) -> dict:
    s = svc.get_session(session_slug, project_slug=slug)
    if not s:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_slug}' not found in project '{slug}'",
        )
    return s.model_dump()


@router.post("/projects/{slug}/sessions")
def create_session(
    slug: str,
    body: dict,
    kind: str = "chat",
) -> dict:
    p = svc.get_project(slug)
    if not p:
        raise HTTPException(status_code=404, detail=f"Project '{slug}' not found")

    s = svc.create_session(body.get("title", ""), project_slug=slug, kind=kind)
    return s.model_dump()


@router.post("/projects/{slug}/sessions/{session_slug}/append")
def append_turn(
    slug: str,
    session_slug: str,
    data: TurnAppend,
) -> dict:
    s = svc.get_session(session_slug, project_slug=slug)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    svc.append_turn(s, data)
    return {"status": "ok"}


@router.post("/projects/{slug}/sessions/{session_slug}/close")
def close_session(
    slug: str,
    session_slug: str,
    data: Optional[SessionClose] = None,
) -> dict:
    s = svc.get_session(session_slug, project_slug=slug)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    s = svc.close_session(s, data)
    return s.model_dump()


@router.post("/projects/{slug}/sessions/{session_slug}/move")
def move_session(
    slug: str,
    session_slug: str,
    body: dict,
) -> dict:
    s = svc.get_session(session_slug, project_slug=slug)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    s = svc.move_session(s, body.get("new_project"))
    return s.model_dump()


# ── Home (no project) ────────────────────────────────────────────────────


@router.post("/chats/sessions")
def create_home_session(
    body: dict,
) -> dict:
    s = svc.create_session(body.get("title", ""), project_slug=None)
    return s.model_dump()


@router.post("/chats/sessions/{session_slug}/append")
def append_home_turn(
    session_slug: str,
    data: TurnAppend,
) -> dict:
    s = svc.get_session(session_slug)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    svc.append_turn(s, data)
    return {"status": "ok"}


@router.post("/chats/sessions/{session_slug}/close")
def close_home_session(
    session_slug: str,
    data: Optional[SessionClose] = None,
) -> dict:
    s = svc.get_session(session_slug)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    s = svc.close_session(s, data)
    return s.model_dump()


# ── Sync / Admin ─────────────────────────────────────────────────────────


@router.get("/sync/conflicts")
def list_sync_conflicts() -> list[dict]:
    from sunny.watcher import get_sync_conflicts, clear_sync_conflicts
    return get_sync_conflicts()


@router.post("/sync/conflicts/clear")
def clear_sync_conflicts_endpoint() -> dict:
    from sunny.watcher import clear_sync_conflicts
    clear_sync_conflicts()
    return {"status": "ok"}
