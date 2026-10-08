"""Chat router API — endpoints for chat sessions.

Handles message routing, LLM calls, and streaming responses.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from sunny.llm.gateway import MODEL_DEFAULT, chat_completion, streaming_chat
from sunny.llm.prompt_assembly import assemble_prompt
from sunny.llm.close_hook import run_close_hook
from sunny.llm.tools import ChatToolRegistry
from sunny.projects.service import create_session as _create_session, append_turn as _append_turn, close_session as _close_session
from sunny.projects.models import ProjectCreate, TurnAppend, SessionClose

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])
tool_registry = ChatToolRegistry()


@router.post("/chats/sessions")
def create_session(
    body: dict,
) -> dict:
    """Create a new session (Home or project-scoped)."""
    title = body.get("title", "Untitled")
    project_slug = body.get("project_slug")
    kind = body.get("kind", "chat")

    try:
        session = _create_session(title, project_slug=project_slug, kind=kind)
        return session.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chats/sessions")
def list_home_sessions() -> list[dict]:
    """List Home sessions."""
    from sunny.projects.service import list_sessions
    sessions = list_sessions(None)
    return [s.model_dump() for s in sessions]


@router.get("/projects/{slug}/sessions")
def list_project_sessions(slug: str) -> list[dict]:
    """List sessions in a project."""
    from sunny.projects.service import list_sessions
    sessions = list_sessions(slug)
    return [s.model_dump() for s in sessions]


@router.post("/chats/sessions/{session_slug}/append")
def append_home_turn(session_slug: str, body: dict) -> dict:
    """Append a turn to a Home session."""
    try:
        turn = TurnAppend(
            role=body.get("role", "Keaton"),
            content=body.get("content", ""),
            mode=body.get("mode", "text"),
        )
        from sunny.projects.service import append_turn
        append_turn(session_slug, turn, project_slug=None)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{slug}/sessions/{session_slug}/append")
def append_project_turn(slug: str, session_slug: str, body: dict) -> dict:
    """Append a turn to a project session."""
    try:
        turn = TurnAppend(
            role=body.get("role", "Keaton"),
            content=body.get("content", ""),
            mode=body.get("mode", "text"),
        )
        from sunny.projects.service import append_turn
        append_turn(session_slug, turn, project_slug=slug)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chats/sessions/{session_slug}/close")
def close_home_session(session_slug: str, body: dict = {}) -> dict:
    """Close a Home session."""
    try:
        result = SessionClose(
            summary=body.get("summary", ""),
            decisions=body.get("decisions", []),
            topics=body.get("topics", []),
            entities=body.get("entities", []),
            open_questions=body.get("open_questions", []),
        )
        from sunny.projects.service import close_session
        session = close_session(session_slug, result, project_slug=None)
        return session.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{slug}/sessions/{session_slug}/close")
def close_project_session(slug: str, session_slug: str, body: dict = {}) -> dict:
    """Close a project session."""
    try:
        result = SessionClose(
            summary=body.get("summary", ""),
            decisions=body.get("decisions", []),
            topics=body.get("topics", []),
            entities=body.get("entities", []),
            open_questions=body.get("open_questions", []),
        )
        from sunny.projects.service import close_session
        session = close_session(session_slug, result, project_slug=slug)
        return session.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chats/sessions/{session_slug}/chat")
def chat_completion_endpoint(
    session_slug: str,
    body: dict,
) -> dict:
    """Send a message and get a chat response.

    Assembles the prompt, calls the LLM, and streams the response.
    """
    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Get session info
    project_slug = body.get("project_slug")

    # Assemble the prompt
    messages = assemble_prompt(
        message=message,
        project_slug=project_slug,
        session_slug=session_slug,
    )

    # Call the LLM
    try:
        result = chat_completion(
            messages=messages,
            model=MODEL_DEFAULT,
            purpose="chat",
        )
        return {
            "reply": result.get("content", ""),
            "usage": {
                "prompt_tokens": result.get("prompt_tokens", 0),
                "completion_tokens": result.get("completion_tokens", 0),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chats/sessions/{session_slug}/stream")
def chat_stream_endpoint(
    session_slug: str,
    body: dict,
):
    """Stream a chat response.

    Yields text chunks as they arrive.
    """
    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    project_slug = body.get("project_slug")

    async def generate():
        messages = assemble_prompt(
            message=message,
            project_slug=project_slug,
            session_slug=session_slug,
        )

        try:
            async for chunk in streaming_chat(messages):
                yield chunk
        except Exception as e:
            yield f"[Error: {e}]"

    return StreamingResponse(generate(), media_type="text/plain")


@router.post("/chats/sessions/{session_slug}/summarize")
def summarize_session(session_slug: str, body: dict = {}) -> dict:
    """Run the close hook on a session.

    Generates summary, merges context, re-indexes, and commits.
    """
    transcript = body.get("transcript", "")
    project_slug = body.get("project_slug")

    result = run_close_hook(
        session_slug,
        project_slug=project_slug,
        session_transcript=transcript,
    )

    return {
        "success": result.success,
        "summary": result.summary,
        "topics": result.topics,
        "summary_pending": result.summary_pending,
    }
