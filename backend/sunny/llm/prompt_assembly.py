"""Prompt assembly — builds the full prompt for LLM calls.

Assembly order (token-budgeted):
1. System: docs/instructions/<purpose>.md + personality dials
2. memory/profile.md (human-owned)
3. memory/personal-context.md
4. Project context.md (if in a project)
5. Retrieved chunks: search(message, project=current), top 6, deduped
6. Current session: last N turns verbatim; older turns by rolling summary
7. The message

Every section is loaded from disk. Missing files are silently skipped.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from sunny.llm.gateway import MODEL_DEFAULT, MODEL_FAST

log = logging.getLogger(__name__)

# Max tokens per section (rough guide)
MAX_PROFILE_TOKENS = 500
MAX_PERSONAL_CONTEXT_TOKENS = 500
MAX_PROJECT_CONTEXT_TOKENS = 1500
MAX_RETRIEVED_CHUNKS_TOKENS = 1000
MAX_SESSION_TURNS = 10  # last N turns


def assemble_prompt(
    message: str,
    *,
    system_purpose: str = "chat",
    project_slug: Optional[str] = None,
    session_slug: Optional[str] = None,
    retrieved_chunks: Optional[list[dict]] = None,
    session_history: Optional[list[dict]] = None,
    session_summary: str = "",
    model: str = MODEL_DEFAULT,
) -> list[dict]:
    """Build the full messages list for an LLM call.

    Args:
        message: The user's current message.
        system_purpose: Purpose identifier for loading the system prompt (chat, research, etc.).
        project_slug: Current project slug (None for Home).
        session_slug: Current session slug.
        retrieved_chunks: Chunks from search results.
        session_history: Previous turns in this session.
        session_summary: Summary of older turns (when session exceeds MAX_SESSION_TURNS).
        model: Model being used (affects prompt length).

    Returns:
        List of {role, content} dicts ready for the API.
    """
    messages: list[dict] = []

    # 1. System prompt
    system = _load_system_prompt(system_purpose)
    messages.append({"role": "system", "content": system})

    # 2. Profile (human-owned)
    profile_text = _load_file("memory/profile.md")
    if profile_text:
        messages.append({"role": "user", "content": f"## Memory Profile\n{profile_text}"})

    # 3. Personal context
    personal_context = _load_file("memory/personal-context.md")
    if personal_context:
        messages.append({"role": "user", "content": f"## Personal Context\n{personal_context}"})

    # 4. Project context
    if project_slug:
        ctx = _load_project_context(project_slug)
        if ctx:
            messages.append({"role": "user", "content": f"## Project Context: {project_slug}\n{ctx}"})

    # 5. Retrieved chunks
    if retrieved_chunks:
        chunks_text = _format_chunks(retrieved_chunks)
        if chunks_text:
            messages.append({"role": "user", "content": f"## Retrieved Context\n{chunks_text}"})

    # 6. Session history
    if session_history:
        hist_text = _format_session_history(session_history, session_summary)
        if hist_text:
            messages.append({"role": "user", "content": f"## Current Session\n{hist_text}"})

    # 7. The message
    messages.append({"role": "user", "content": message})

    return messages


def _load_system_prompt(purpose: str) -> str:
    """Load the system prompt for the given purpose."""
    # Try loading from docs/instructions/<purpose>.md
    prompt_path = Path("vault") / "docs" / "instructions" / f"{purpose}.md"
    if prompt_path.exists():
        try:
            content = prompt_path.read_text(encoding="utf-8")
            log.info("Loaded system prompt from %s", prompt_path)
            return content
        except OSError:
            log.warning("Failed to read system prompt from %s", prompt_path)

    # Fallback to inline system prompt
    return _default_system_prompt(purpose)


def _default_system_prompt(purpose: str) -> str:
    """Default system prompt when no file is found."""
    base = """You are Sunny, a personal AI assistant.

Guidelines:
- JARVIS/Muse personality: competent, calm, dry, precise
- No emoji, no exclamation marks, no filler phrases
- Facts first, shortest accurate phrasing
- Uncertainty stated plainly
- Dry humor allowed sparingly, drawing on tier-3 running references
"""
    if purpose == "research":
        base += "\n\nResearch mode: Ground answers in provided sources. Cite [S<n> §<section>] for source claims."
    elif purpose == "summarize":
        base += "\n\nSummarization mode: Produce concise summaries ≤120 words."
    elif purpose == "ideas":
        base += "\n\nIdeas mode: Expand, attack, and refine ideas. Questions before suggestions."

    return base


def _load_file(relative_path: str) -> Optional[str]:
    """Load a file from the vault, returning None if missing."""
    path = Path("vault") / relative_path
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        log.warning("Failed to read %s", relative_path)
    return None


def _load_project_context(project_slug: str) -> Optional[str]:
    """Load a project's context.md file."""
    content = _load_file(f"projects/{project_slug}/context.md")
    if not content:
        log.info("No context.md found for project %s", project_slug)
    return content


def _format_chunks(chunks: list[dict]) -> str:
    """Format retrieved chunks as text with metadata."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks):
        path = chunk.get("path", "")
        project = chunk.get("project", "")
        kind = chunk.get("kind", "file")
        text = chunk.get("text", "")

        meta = f"[{kind}"
        if project:
            meta += f" project={project}"
        if path:
            meta += f" path={path}"
        meta += "]"

        parts.append(f"### Chunk {i + 1} {meta}\n{text}")

    return "\n\n".join(parts)


def _format_session_history(history: list[dict], summary: str = "") -> str:
    """Format session history for the prompt.

    If history exceeds MAX_SESSION_TURNS, use the summary for older turns.
    """
    if not history:
        return ""

    # If we have a summary, show it instead of full history
    if summary and len(history) > MAX_SESSION_TURNS:
        return f"### Previous turns (summarized)\n{summary}\n\n### Recent turns\n" + _format_turns(history[-MAX_SESSION_TURNS:])

    return "### Session history\n" + _format_turns(history)


def _format_turns(turns: list[dict]) -> str:
    """Format a list of turns into text."""
    parts: list[str] = []
    for turn in turns:
        role = turn.get("role", "unknown")
        content = turn.get("content", "")
        parts.append(f"### {role}\n{content}")
    return "\n\n".join(parts)
