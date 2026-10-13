"""Chat router API — endpoints for chat sessions.

Handles message routing, LLM calls, and streaming responses. Session CRUD (create, list, append,
close) lives in sunny.projects.router; this module adds the endpoints that talk to Claude.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from sunny.config import vault_root
from sunny.frontmatter import load
from sunny.llm.close_hook import run_close_hook
from sunny.llm.gateway import chat_completion, streaming_chat
from sunny.llm.prompt_assembly import assemble_prompt
from sunny.llm.tools import ChatToolRegistry
from sunny.projects import service as svc
from sunny.projects.models import Session, TurnAppend
from sunny.vault.io import read_file

log = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])
tool_registry = ChatToolRegistry()

# Matches the turn headers written by Session.append_turn: "### Keaton · 14:02 · text"
_TURN_RE = re.compile(r"^### (?P<role>[^·\n]+?) · \d{2}:\d{2} · \w+\s*$", re.MULTILINE)


def _session_or_404(session_slug: str, project_slug: Optional[str]) -> Session:
    session = svc.get_session(session_slug, project_slug=project_slug)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def session_history(session: Session) -> list[dict]:
    """Parse the turns recorded in a session file into [{role, content}]."""
    text = read_file(session._resolve_path(vault_root())) or ""
    body = load(text).content
    matches = list(_TURN_RE.finditer(body))
    turns = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        turns.append({"role": m.group("role").strip(), "content": body[m.end():end].strip()})
    return turns


def _prepare(session_slug: str, body: dict) -> tuple[Session, list[dict]]:
    """Validate the request, record Keaton's turn and assemble the prompt."""
    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    project_slug = body.get("project_slug")
    session = _session_or_404(session_slug, project_slug)

    history = session_history(session)
    svc.append_turn(session, TurnAppend(role="Keaton", content=message, mode=body.get("mode", "text")))
    messages = assemble_prompt(
        message=message,
        project_slug=project_slug,
        session_slug=session_slug,
        session_history=history,
        session_summary=session.summary,
    )
    return session, messages


def _with_turns(session: Session) -> dict:
    return {"session": session.model_dump(), "turns": session_history(session)}


@router.get("/chats/sessions/{session_slug}")
def get_home_session(session_slug: str) -> dict:
    """A Home session with its recorded turns."""
    return _with_turns(_session_or_404(session_slug, None))


@router.get("/projects/{slug}/sessions/{session_slug}/turns")
def get_project_session_turns(slug: str, session_slug: str) -> dict:
    """A project session with its recorded turns."""
    return _with_turns(_session_or_404(session_slug, slug))


@router.post("/chats/sessions/{session_slug}/chat")
async def chat_completion_endpoint(session_slug: str, body: dict) -> dict:
    """Send a message and get a chat response."""
    session, messages = _prepare(session_slug, body)
    try:
        result = await chat_completion(messages=messages, purpose="chat")
    except Exception as e:
        log.error("Chat failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Claude request failed")

    if result.get("spend_blocked"):
        raise HTTPException(status_code=429, detail="Claude spend cap reached")
    reply = result.get("content", "")
    svc.append_turn(session, TurnAppend(role="Sunny", content=reply))
    return {
        "reply": reply,
        "usage": {
            "prompt_tokens": result.get("prompt_tokens", 0),
            "completion_tokens": result.get("completion_tokens", 0),
        },
    }


def _sse(payload: dict | str) -> str:
    return f"data: {payload if isinstance(payload, str) else json.dumps(payload)}\n\n"


@router.post("/chats/sessions/{session_slug}/stream")
def chat_stream_endpoint(session_slug: str, body: dict):
    """Stream a chat response as server-sent events: {"text": ...} chunks, then [DONE]."""
    session, messages = _prepare(session_slug, body)

    async def generate():
        parts: list[str] = []
        try:
            async for chunk in streaming_chat(messages):
                parts.append(chunk)
                yield _sse({"text": chunk})
        except Exception as e:
            log.error("Streaming chat failed: %s", type(e).__name__)
            yield _sse({"error": "Claude request failed"})
        reply = "".join(parts)
        if reply:
            svc.append_turn(session, TurnAppend(role="Sunny", content=reply))
        yield _sse("[DONE]")

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/chats/sessions/{session_slug}/summarize")
def summarize_session(session_slug: str, body: dict = {}) -> dict:
    """Run the close hook on a session.

    Generates summary, merges context, re-indexes, and commits.
    """
    project_slug = body.get("project_slug")
    transcript = body.get("transcript", "")
    if not transcript:
        session = svc.get_session(session_slug, project_slug=project_slug)
        if session:
            transcript = "\n\n".join(f"{t['role']}: {t['content']}" for t in session_history(session))

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
