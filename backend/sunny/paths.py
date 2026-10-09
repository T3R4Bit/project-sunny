"""Vault path utilities — canonical layout from §5.1."""

from __future__ import annotations

from pathlib import Path


def project_dir(vault: Path, slug: str) -> Path:
    """Return the directory for a project slug."""
    return vault / "projects" / slug


def project_file(vault: Path, slug: str, name: str = "project.md") -> Path:
    return project_dir(vault, slug) / name


def context_file(vault: Path, slug: str) -> Path:
    return project_dir(vault, slug) / "context.md"


def sessions_dir(vault: Path, slug: str) -> Path:
    return project_dir(vault, slug) / "sessions"


def session_file(vault: Path, slug: str, filename: str) -> Path:
    return sessions_dir(vault, slug) / filename


def home_chats_dir(vault: Path) -> Path:
    return vault / "chats"


def home_session_file(vault: Path, filename: str) -> Path:
    return home_chats_dir(vault) / filename


def research_dir(vault: Path, slug: str) -> Path:
    return vault / "research" / slug


def personal_context_file(vault: Path) -> Path:
    return vault / "memory" / "personal-context.md"


def profile_file(vault: Path) -> Path:
    return vault / "memory" / "profile.md"


def reports_dir(vault: Path, kind: str) -> Path:
    return vault / "reports" / kind


def facts_dir(vault: Path) -> Path:
    return vault / "memory" / "facts"


def facts_file(vault: Path, date: str) -> Path:
    return facts_dir(vault) / f"{date}.md"


def log_dir(vault: Path) -> Path:
    return vault / "log"


def routing_log(vault: Path) -> Path:
    return log_dir(vault) / "routing.md"


def extraction_log(vault: Path) -> Path:
    return log_dir(vault) / "extraction.md"


def llm_usage_log(vault: Path) -> Path:
    return log_dir(vault) / "llm-usage.md"


def tasks_queue_dir(vault: Path) -> Path:
    return vault / "tasks-queue"


def tools_dir(vault: Path) -> Path:
    return vault / "tools"


def ideas_dir(vault: Path) -> Path:
    return vault / "ideas"


def ideas_auto_dir(vault: Path) -> Path:
    return vault / "ideas-auto"


def recipes_dir(vault: Path) -> Path:
    return vault / "recipes"


def docs_dir(vault: Path) -> Path:
    return vault / "docs"


def instructions_dir(vault: Path) -> Path:
    return docs_dir(vault) / "instructions"


def instructions_file(vault: Path, name: str) -> Path:
    return instructions_dir(vault) / name


def research_sessions_dir(vault: Path, research_slug: str) -> Path:
    return research_dir(vault, research_slug) / "sessions"


def research_sources_dir(vault: Path, research_slug: str) -> Path:
    return research_dir(vault, research_slug) / "sources"


def research_source_dir(vault: Path, research_slug: str, source_id: str) -> Path:
    return research_sources_dir(vault, research_slug) / source_id


def lookups_dir(vault: Path) -> Path:
    return research_dir(vault) / "_lookups"


SYNC_CONFLICT_SUFFIX = ".sync-conflict-*"
