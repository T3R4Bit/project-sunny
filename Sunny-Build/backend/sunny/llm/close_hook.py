"""Session close hook — runs on every session close.

Per §6.3:
1. One DEFAULT-model call with JSON schema produces summary, topics, entities, decisions, open_questions, personal_facts
2. Write fields into session frontmatter
3. Merge project-relevant items into project's context.md
4. Merge personal items into memory/personal-context.md
5. Run extraction rules
6. Re-index the session
7. Git commit

If the call fails or spend cap blocks it, mark session closed with summary_pending=true.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from sunny.llm.gateway import MODEL_DEFAULT, chat_completion, SpendStatus
from sunny.vault.io import read_file, atomic_write
from sunny.frontmatter import load, dump
from sunny.index.service import index_text, init_index
from sunny.config import get_settings
from sunny.extraction.rules_engine import RulesEngine, RulesParser, ExtractionLog, write_fact

log = logging.getLogger(__name__)

# JSON schema for the close hook summary
CLOSE_HOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Session summary, ≤120 words",
        },
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of discussion topics",
        },
        "entities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "People, parts, tools, concepts mentioned",
        },
        "decisions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Dated decisions made in the session",
        },
        "open_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Unresolved questions",
        },
        "personal_facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Things about Keaton rather than the project",
        },
    },
    "required": ["summary", "topics", "entities", "decisions", "open_questions", "personal_facts"],
}

# Section caps for project context.md
CONTEXT_SECTIONS = {
    "state": {"max_items": 1, "max_words": 150},
    "decisions": {"max_items": 30},
    "open_questions": {"max_items": 20},
    "entities": {"max_items": 40},
    "sources": {"max_items": 20},
    "recent_sessions": {"max_items": 10},
    "history": {"max_words": 300},
}

# Session section to merge into context
MERGE_SECTIONS = {
    "decisions": "decisions",
    "open_questions": "open_questions",
    "entities": "entities",
}


@dataclass
class CloseHookResult:
    """Result of a session close hook."""
    success: bool
    summary: str = ""
    topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    personal_facts: list[str] = field(default_factory=list)
    summary_pending: bool = False
    error: str = ""


def run_close_hook(
    session_slug: str,
    *,
    project_slug: Optional[str] = None,
    session_content: str = "",
    session_transcript: str = "",
) -> CloseHookResult:
    """Run the close hook for a session.

    Args:
        session_slug: The session's slug/filename.
        project_slug: Project slug (None for Home sessions).
        session_content: Full session file content (with frontmatter).
        session_transcript: Just the body text of turns.

    Returns:
        CloseHookResult with summary fields and status.
    """
    result = CloseHookResult(success=False)

    # 1. Call LLM for summary
    summary_data = _generate_summary(session_transcript, session_slug, project_slug)

    if summary_data is None:
        # LLM call failed or spend cap blocked
        result.summary_pending = True
        result.error = "LLM call failed or spend cap blocked"
        log.warning("Close hook failed for %s: %s", session_slug, result.error)
        return result

    # Parse the summary data
    result.summary = summary_data.get("summary", "")
    result.topics = summary_data.get("topics", [])
    result.entities = summary_data.get("entities", [])
    result.decisions = summary_data.get("decisions", [])
    result.open_questions = summary_data.get("open_questions", [])
    result.personal_facts = summary_data.get("personal_facts", [])

    # 2. Write fields into session frontmatter
    _update_session_frontmatter(session_slug, project_slug, result)

    # 3. Merge project-relevant items into context.md
    if project_slug:
        _merge_to_project_context(project_slug, result)

    # 4. Merge personal items into personal-context.md
    if result.personal_facts:
        _merge_to_personal_context(result)

    # 5. Run extraction rules (stub — P7)
    _run_extraction(session_transcript, session_slug)

    # 6. Re-index the session
    _reindex_session(session_slug, project_slug, session_transcript)

    # 7. Git commit
    _git_commit(project_slug, session_slug, result)

    result.success = True
    return result


def _generate_summary(
    transcript: str,
    session_slug: str,
    project_slug: Optional[str],
) -> Optional[dict]:
    """Call the LLM to generate session summary data."""
    if not transcript.strip():
        return {
            "summary": "No content to summarize.",
            "topics": [],
            "entities": [],
            "decisions": [],
            "open_questions": [],
            "personal_facts": [],
        }

    system_prompt = """You are summarizing a chat session. Produce a JSON object with:
- summary: ≤120 words capturing what was discussed
- topics: list of discussion topics
- entities: people, parts, tools, concepts
- decisions: dated decisions made
- open_questions: unresolved questions
- personal_facts: things about Keaton (not the project)

Keep it factual. No fluff."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Summarize this session:\n\n{transcript[:4000]}"},
    ]

    try:
        result = chat_completion(
            messages=messages,
            model=MODEL_DEFAULT,
            json_schema=CLOSE_HOOK_SCHEMA,
            purpose="session_summary",
        )

        content = result.get("content", "")
        if result.get("spend_blocked"):
            return None

        import json
        try:
            return json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            log.warning("Failed to parse summary JSON: %s", content[:200])
            return None
    except Exception as e:
        log.error("Summary generation failed: %s", e)
        return None


def _update_session_frontmatter(
    session_slug: str,
    project_slug: Optional[str],
    result: CloseHookResult,
) -> None:
    """Write summary fields into the session file's frontmatter."""
    if project_slug:
        path = Path("vault") / "projects" / project_slug / "sessions" / f"{session_slug}.md"
    else:
        path = Path("vault") / "chats" / f"{session_slug}.md"

    if not path.exists():
        log.warning("Session file not found for frontmatter update: %s", path)
        return

    try:
        post = load(path.read_text(encoding="utf-8"))
        post.content = post.content  # preserve body

        # Update frontmatter fields
        post.meta["summary"] = result.summary
        post.meta["topics"] = result.topics
        post.meta["entities"] = result.entities
        post.meta["decisions"] = result.decisions
        post.meta["open_questions"] = result.open_questions
        post.meta["summary_pending"] = result.summary_pending
        post.meta["status"] = "summarized" if not result.summary_pending else "closed"

        atomic_write(path, dump(post))
    except Exception as e:
        log.error("Failed to update session frontmatter: %s", e)


def _merge_to_project_context(project_slug: str, result: CloseHookResult) -> None:
    """Merge session items into project's context.md."""
    context_path = Path("vault") / "projects" / project_slug / "context.md"
    if not context_path.exists():
        return

    try:
        content = context_path.read_text(encoding="utf-8")
        post = load(content)
        body = post.content if hasattr(post, "content") else content

        for section_key, meta_key in MERGE_SECTIONS.items():
            items = getattr(result, meta_key, [])
            if items:
                body = _merge_section(body, section_key, items)

        # Update recent_sessions: add this session
        body = _add_recent_session(body, project_slug, result.summary)

        post.content = body
        atomic_write(context_path, dump(post))
    except Exception as e:
        log.error("Failed to merge to project context: %s", e)


def _merge_section(body: str, section: str, items: list[str]) -> str:
    """Merge items into a marked section, respecting caps.

    If the section doesn't exist, appends a new marked block.
    """
    marker_pattern = rf"<!-- sunny:begin section={section} -->.*?<!-- sunny:end section={section} -->"
    match = re.search(marker_pattern, body, re.DOTALL)

    if match:
        existing = match.group()
        # Extract existing items (lines starting with - or *)
        existing_items = re.findall(r"^[\-\*]\s+(.+)$", existing, re.MULTILINE)

        # Add new items
        new_items = [f"- {item}" for item in items]
        all_items = existing_items + new_items

        # Apply cap
        cap = CONTEXT_SECTIONS.get(section, {}).get("max_items", 999)
        capped_items = all_items[-cap:]

        # Rebuild section
        new_section = f"<!-- sunny:begin section={section} -->\n"
        new_section += "\n".join(capped_items) + "\n"
        new_section += f"<!-- sunny:end section={section} -->"

        body = body[:match.start()] + new_section + body[match.end():]
    else:
        # Append new section
        new_section = f"\n<!-- sunny:begin section={section} -->\n"
        new_section += "\n".join(f"- {item}" for item in items[:CONTEXT_SECTIONS.get(section, {}).get("max_items", 30)]) + "\n"
        new_section += f"<!-- sunny:end section={section} -->"
        body += new_section

    return body


def _add_recent_session(body: str, project_slug: str, summary: str) -> str:
    """Add a session to the recent_sessions section."""
    marker_pattern = r"<!-- sunny:begin section=recent_sessions -->.*?<!-- sunny:end section=recent_sessions -->"
    match = re.search(marker_pattern, body, re.DOTALL)

    import datetime
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    session_line = f"- {date_str}: {summary[:80]}"

    if match:
        existing = match.group()
        items = re.findall(r"^[\-\*]\s+(.+)$", existing, re.MULTILINE)
        items.insert(0, session_line)
        items = items[:10]  # cap at 10

        new_section = f"<!-- sunny:begin section=recent_sessions -->\n"
        new_section += "\n".join(items) + "\n"
        new_section += f"<!-- sunny:end section=recent_sessions -->"

        body = body[:match.start()] + new_section + body[match.end():]
    else:
        new_section = f"\n<!-- sunny:begin section=recent_sessions -->\n{session_line}\n<!-- sunny:end section=recent_sessions -->"
        body += new_section

    return body


def _merge_to_personal_context(result: CloseHookResult) -> None:
    """Merge personal facts into memory/personal-context.md."""
    path = Path("vault") / "memory" / "personal-context.md"
    if not path.exists():
        return

    try:
        content = path.read_text(encoding="utf-8")
        post = load(content)
        body = post.content if hasattr(post, "content") else content

        for fact in result.personal_facts:
            body = _merge_section(body, "current_focus", [fact])

        post.content = body
        atomic_write(path, dump(post))
    except Exception as e:
        log.error("Failed to merge to personal context: %s", e)


def _run_extraction(transcript: str, session_slug: str) -> None:
    """Run extraction rules over the transcript using the P7 rules engine."""
    if not transcript.strip():
        return

    settings = get_settings()
    vault = settings.vault_path

    # Load rules from file
    rules_path = vault / "docs" / "extraction-rules.md"
    if not rules_path.exists():
        log.warning("Extraction rules file not found: %s", rules_path)
        return

    try:
        rules_content = rules_path.read_text(encoding='utf-8')
        parser = RulesParser()
        rules = parser.parse(rules_content)
        if not rules:
            log.warning('No valid extraction rules loaded')
            return

        engine = RulesEngine()
        engine.set_rules(rules)

        # Match rules against transcript
        matches = engine.match(transcript, session_slug)
        if not matches:
            return

        # Classify by gate
        classified = engine.classify(matches)

        # Log all decisions
        log_writer = ExtractionLog(vault)
        for match in classified['auto_write']:
            log_writer.log_decision(match, 'auto_write')
            write_fact(vault, match)
            log.info('Auto-wrote fact for session %s: %s (tier=%d)', session_slug, match.rule_name, match.tier)

        for match in classified['approve_queue']:
            log_writer.log_decision(match, 'approve_queue')
            log.info('Queued for approval: %s (session=%s, tier=%d)', match.rule_name, session_slug, match.tier)

        for match in classified['log_only']:
            log_writer.log_decision(match, 'log_only')
            log.debug('Logged only: %s (session=%s, tier=%d)', match.rule_name, session_slug, match.tier)

        log.info('Extraction complete for session %s: %d matches (%d auto, %d queue, %d log)',
                 session_slug, len(matches), len(classified['auto_write']),
                 len(classified['approve_queue']), len(classified['log_only']))

    except Exception as e:
        log.error('Extraction failed for session %s: %s', session_slug, e)


def _reindex_session(session_slug: str, project_slug: Optional[str], transcript: str) -> None:
    """Re-index the session after summary."""
    try:
        settings = get_settings()
        db_path = Path(settings.db_path)
        init_index(db_path)
        conn = __import__("sqlite3").connect(str(db_path))
        try:
            from sunny.index.chunker import chunk_session_file
            chunks = chunk_session_file(transcript, session_slug, project=project_slug)
            for chunk in chunks:
                from sunny.index.service import index_chunk
                index_chunk(conn, chunk)
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        log.warning("Failed to reindex session %s: %s", session_slug, e)


def _git_commit(project_slug: Optional[str], session_slug: str, result: CloseHookResult) -> None:
    """Git commit the vault changes."""
    try:
        import subprocess
        vault_path = Path("vault")

        # Stage changed files
        subprocess.run(
            ["git", "add", "."],
            cwd=str(vault_path),
            capture_output=True,
        )

        # Commit
        sections = []
        if result.decisions:
            sections.append(f"{len(result.decisions)} decisions")
        if result.open_questions:
            sections.append(f"{len(result.open_questions)} open questions")

        if sections:
            msg = f"summary: {session_slug} — {', '.join(sections)}"
        else:
            msg = f"summary: {session_slug}"

        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=str(vault_path),
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        log.warning("Git commit failed for session close: %s", e)
