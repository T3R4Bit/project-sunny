"""Projects — business logic for project and session CRUD."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sunny.config import get_settings
from sunny.paths import (
    context_file,
    facts_dir,
    personal_context_file,
    project_dir,
    project_file,
    sessions_dir,
)
from sunny.projects.models import (
    Project,
    ProjectCreate,
    ProjectUpdate,
    Session,
    SessionClose,
    TurnAppend,
)
from sunny.vault.git_ops import commit as git_commit, init_repo
from sunny.vault.io import (
    atomic_write,
    ensure_markers,
    file_hash,
    merge_shared_file,
    read_file,
)

log = logging.getLogger(__name__)


def _vault() -> Path:
    return get_settings().vault_path


def _init_vault_git() -> Path:
    vault = _vault()
    vault.mkdir(parents=True, exist_ok=True)
    init_repo(vault)
    return vault


# ── Projects ─────────────────────────────────────────────────────────────


def list_projects() -> list[Project]:
    """Return all projects from disk."""
    vault = _vault()
    projects_dir = vault / "projects"
    if not projects_dir.exists():
        return []
    projects = []
    for md in projects_dir.glob("*/project.md"):
        if md.exists():
            try:
                projects.append(Project.from_frontmatter(md))
            except Exception:
                log.exception("Failed to parse project at %s", md)
    return projects


def get_project(slug: str) -> Optional[Project]:
    """Return a single project by slug, or None."""
    vault = _vault()
    pf = project_file(vault, slug)
    if not pf.exists():
        return None
    try:
        return Project.from_frontmatter(pf)
    except Exception:
        log.exception("Failed to parse project %s", slug)
        return None


def create_project(data: ProjectCreate) -> Project:
    """Create a new project on disk and git-commit it."""
    vault = _init_vault_git()
    slug = data.slug

    # Reject if already exists
    existing = get_project(slug)
    if existing:
        raise ValueError(f"Project '{slug}' already exists")

    project = Project(
        id=ulid("prj"),
        slug=slug,
        title=data.title,
        kind=data.kind,
        tags=data.tags,
    )

    # Create project.md with frontmatter
    pf = project_file(vault, slug)
    pf.parent.mkdir(parents=True, exist_ok=True)
    project.save(vault)

    # Create context.md with marker sections
    cf = context_file(vault, slug)
    _create_initial_context(cf)

    # Create sessions dir
    sessions_dir(vault, slug).mkdir(parents=True, exist_ok=True)

    # Git commit
    git_commit(vault, f"project: create '{slug}' — {data.title}")

    log.info("Created project %s", slug)
    return project


def update_project(slug: str, data: ProjectUpdate) -> Optional[Project]:
    """Update an existing project. Returns None if not found."""
    project = get_project(slug)
    if not project:
        return None

    if data.title is not None:
        project.title = data.title
    if data.kind is not None:
        project.kind = data.kind
    if data.status is not None:
        project.status = data.status
    if data.tags is not None:
        project.tags = data.tags

    vault = _vault()
    project.save(vault)
    git_commit(vault, f"project: update '{slug}'")
    return project


def delete_project(slug: str) -> bool:
    """Delete a project directory and git-commit. Returns True on success."""
    project = get_project(slug)
    if not project:
        return False

    vault = _vault()
    proj_dir = project_dir(vault, slug)
    if proj_dir.exists():
        import shutil
        shutil.rmtree(proj_dir)

    git_commit(vault, f"project: delete '{slug}'")
    log.info("Deleted project %s", slug)
    return True


def archive_project(slug: str) -> bool:
    """Set project status to archived."""
    return update_project(slug, ProjectUpdate(status="archived")) is not None


# ── Sessions ─────────────────────────────────────────────────────────────


def list_sessions(project_slug: Optional[str] = None) -> list[Session]:
    """List all sessions, optionally scoped to a project."""
    vault = _vault()
    sessions = []

    if project_slug:
        sd = sessions_dir(vault, project_slug)
    else:
        # Home sessions
        from sunny.paths import home_chats_dir
        sd = home_chats_dir(vault)

    if not sd.exists():
        return sessions

    for md in sd.glob("*.md"):
        try:
            s = Session.from_frontmatter(md)
            if project_slug:
                s.project_slug = project_slug
            sessions.append(s)
        except Exception:
            log.exception("Failed to parse session %s", md)

    sessions.sort(key=lambda s: s.started or "", reverse=True)
    return sessions


def get_session(slug: str, project_slug: Optional[str] = None) -> Optional[Session]:
    """Get a session by slug."""
    vault = _vault()

    if project_slug:
        sd = sessions_dir(vault, project_slug)
    else:
        from sunny.paths import home_chats_dir
        sd = home_chats_dir(vault)

    for md in sd.glob("*.md"):
        if md.stem == slug:
            try:
                s = Session.from_frontmatter(md)
                if project_slug:
                    s.project_slug = project_slug
                return s
            except Exception:
                log.exception("Failed to parse session %s", md)
                return None
    return None


def create_session(
    title: str,
    project_slug: Optional[str] = None,
    kind: str = "chat",
) -> Session:
    """Create a new session and return it."""
    vault = _init_vault_git()
    session = Session(
        id=ulid("ses"),
        slug="",
        title=title,
        project_slug=project_slug,
        kind=kind,
    )

    # Save (this sets slug and filename)
    session.save(vault)
    session.slug = Path(session.save(vault)).stem

    git_commit(vault, f"session: create '{title}'")
    log.info("Created session %s (project=%s)", session.slug, project_slug)
    return session


def append_turn(session: Session, data: TurnAppend) -> None:
    """Append a turn to a live session."""
    session.append_turn(_vault(), data.role, data.content, data.mode)


def close_session(session: Session, close_data: Optional[SessionClose] = None) -> Session:
    """Close a session and update frontmatter.

    If close_data is provided, uses it directly (manual close).
    Otherwise calls the LLM close hook for automatic summarization.
    """
    vault = _vault()
    session.ended = now_iso()

    if close_data:
        # Manual close with provided data
        session.summary = close_data.summary
        session.topics = close_data.topics
        session.entities = close_data.entities
        session.decisions = close_data.decisions
        session.open_questions = close_data.open_questions
        session.status = "closed"
        session.save(vault)
        git_commit(vault, f"session: close '{session.title}'")
        log.info("Closed session %s (manual)", session.slug)

        if session.project_slug:
            _merge_session_context(session, close_data)
        if close_data.personal_facts:
            _merge_personal_facts(close_data.personal_facts)
    else:
        # Automatic close via LLM hook
        from sunny.llm.close_hook import run_close_hook

        session_file = session._resolve_path(vault)
        transcript = ""
        if session_file.exists():
            raw = read_file(session_file) or ""
            from sunny.frontmatter import load as fm_load
            try:
                post = fm_load(raw)
                transcript = getattr(post, "content", raw) if hasattr(post, "content") else raw
            except Exception:
                transcript = raw

        hook_result = run_close_hook(
            session.slug,
            project_slug=session.project_slug,
            session_content=read_file(session_file) or "",
            session_transcript=transcript,
        )

        if hook_result.success:
            session.summary = hook_result.summary
            session.topics = hook_result.topics
            session.entities = hook_result.entities
            session.decisions = hook_result.decisions
            session.open_questions = hook_result.open_questions
            session.status = "summarized" if not hook_result.summary_pending else "closed"
        else:
            # LLM failed — mark as closed with summary_pending
            session.status = "closed"
            session.summary_pending = True
            log.warning("Close hook failed for %s: %s", session.slug, hook_result.error)

        session.save(vault)
        git_commit(vault, f"session: close '{session.title}'")
        log.info("Closed session %s", session.slug)

    return session


def move_session(session: Session, new_project_slug: Optional[str]) -> Session:
    """Move a session from one project (or Home) to another."""
    vault = _vault()

    # Determine old path
    if session.project_slug:
        from sunny.paths import sessions_dir as sessions_dir_for
        old_dir = sessions_dir_for(vault, session.project_slug)
    else:
        from sunny.paths import home_chats_dir
        old_dir = home_chats_dir(vault)

    old_path = old_dir / f"{session.slug}.md"
    if not old_path.exists():
        return session

    # Read and update frontmatter
    content = read_file(old_path) or ""
    from sunny.frontmatter import dump, load as fm_load
    post = fm_load(content)
    post.metadata["project"] = new_project_slug

    # Determine new path
    if new_project_slug:
        from sunny.paths import sessions_dir as sessions_dir_for
        new_dir = sessions_dir_for(vault, new_project_slug)
    else:
        from sunny.paths import home_chats_dir
        new_dir = home_chats_dir(vault)

    new_dir.mkdir(parents=True, exist_ok=True)
    new_path = new_dir / f"{session.filename()}"

    atomic_write(new_path, dump(post))

    # Remove old file
    old_path.unlink(missing_ok=True)

    session.project_slug = new_project_slug
    session.slug = new_path.stem
    git_commit(vault, f"session: move '{session.title}' to {new_project_slug or 'Home'}")
    log.info("Moved session %s to %s", session.slug, new_project_slug or "Home")
    return session


# ── Context management ───────────────────────────────────────────────────

CONTEXT_SECTIONS = {
    "state": {"cap": 150, "header": "## state"},
    "decisions": {"cap": 30, "header": "## decisions"},
    "open_questions": {"cap": 20, "header": "## open_questions"},
    "entities": {"cap": 40, "header": "## entities"},
    "sources": {"cap": 20, "header": "## sources"},
    "recent_sessions": {"cap": 10, "header": "## recent_sessions"},
    "history": {"cap": 300, "header": "## history"},
}


def _create_initial_context(path: Path) -> None:
    """Create an empty context.md with marker sections."""
    content = "# Context\n\n"
    for section in CONTEXT_SECTIONS:
        marker = f"<!-- sunny:begin section={section} -->\n\n<!-- sunny:end section={section} -->\n"
        content += f"{CONTEXT_SECTIONS[section]['header']}\n{marker}\n"
    atomic_write(path, content)


def update_context_section(slug: str, section: str, content: str) -> bool:
    """Update a single section in a project's context.md.

    Returns False if external edit detected.
    """
    vault = _vault()
    cf = context_file(vault, slug)
    if not cf.exists():
        _create_initial_context(cf)

    existing = read_file(cf) or ""
    last_hash = file_hash(cf)
    merged, modified = merge_shared_file(
        existing, section, content,
        last_hash=last_hash, current_hash=last_hash,
    )
    if modified:
        atomic_write(cf, merged)
        vault = _vault()
        git_commit(vault, f"context: '{slug}' — {section}")
    return modified


def update_context_sections(slug: str, sections: dict[str, str]) -> int:
    """Update multiple sections. Returns count of successful writes."""
    count = 0
    for section, content in sections.items():
        if update_context_section(slug, section, content):
            count += 1
    return count


def _merge_session_context(session: Session, close_data: SessionClose) -> None:
    """Merge closed session data into project context.md."""
    slug = session.project_slug
    if not slug:
        return

    sections: dict[str, str] = {}

    # State summary
    if close_data.summary:
        sections["state"] = close_data.summary

    # Decisions
    if close_data.decisions:
        existing = get_machine_section(slug, "decisions")
        for d in close_data.decisions:
            existing += f"- {d}\n"
        sections["decisions"] = existing

    # Open questions
    if close_data.open_questions:
        existing = get_machine_section(slug, "open_questions")
        for q in close_data.open_questions:
            existing += f"- {q}\n"
        sections["open_questions"] = existing

    # Entities
    if close_data.entities:
        existing = get_machine_section(slug, "entities")
        for e in close_data.entities:
            existing += f"- {e}\n"
        sections["entities"] = existing

    # Recent sessions
    recent = get_machine_section(slug, "recent_sessions")
    recent += f"- [{session.title}]({session.slug}) — {session.started[:10]}\n"
    sections["recent_sessions"] = recent

    if sections:
        update_context_sections(slug, sections)


def _merge_personal_facts(facts: list[str]) -> None:
    """Append personal facts to memory/personal-context.md."""
    vault = _vault()
    pf = personal_context_file(vault)
    if not pf.exists():
        _create_initial_context(pf)

    existing = read_file(pf) or ""
    content = ""
    for f in facts:
        content += f"- {f}\n"

    merged, _ = merge_shared_file(existing, "facts", content)
    atomic_write(pf, merged)


def get_machine_section(slug: str, section: str) -> str:
    """Read the current machine section content from context.md."""
    vault = _vault()
    cf = context_file(vault, slug)
    existing = read_file(cf) or ""
    from sunny.vault.io import get_machine_region
    return get_machine_region(existing, section)


# ── Helpers ──────────────────────────────────────────────────────────────

import secrets
from datetime import datetime, timezone


def ulid(prefix: str) -> str:
    """Generate a pseudo-ULID with a given prefix."""
    return prefix + secrets.token_hex(8)[:13 - len(prefix)] if len(prefix) < 13 else prefix + secrets.token_hex(5)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
