"""Projects — models with frontmatter schemas from §5.4."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import frontmatter as fm
from pydantic import BaseModel, Field, field_validator

from sunny.frontmatter import dump, load
from sunny.paths import (
    context_file,
    home_session_file,
    project_file,
    session_file,
)
from sunny.vault.io import atomic_write, read_file

# Session filename pattern: YYYY-MM-DD-HHMM-title.md
_SESSION_FN_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}-\d{4}-[^.]+)\.md$"
)

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ulid_prefix(prefix: str, n: int = 13) -> str:
    """Generate a pseudo-ID starting with *prefix* followed by random hex.

    Real ULID would need the `ulid` package; this keeps the format compatible
    (prefix + 13 hex chars = project/session slug style).
    """
    import secrets
    return prefix + secrets.token_hex(8)[:n - len(prefix)]


class Project(BaseModel):
    id: str = ""
    slug: str
    title: str
    description: str = ""
    kind: str = "project"  # project | research
    status: str = "active"  # active | long_term | someday | archived
    tags: list[str] = Field(default_factory=list)
    created: str = Field(default_factory=now_iso)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return v.lower().replace(" ", "-").replace("_", "-")

    def to_frontmatter(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "kind": self.kind,
            "status": self.status,
            "tags": self.tags,
            "created": self.created,
        }

    @classmethod
    def from_frontmatter(cls, path: Path) -> Project:
        content = read_file(path) or ""
        post = load(content)
        meta = dict(post.metadata)
        return cls(
            id=meta.get("id", ""),
            slug=meta.get("slug", path.stem),
            title=meta.get("title", path.stem.replace("-", " ").title()),
            kind=meta.get("kind", "project"),
            status=meta.get("status", "active"),
            tags=meta.get("tags", []),
            created=meta.get("created", now_iso()),
        )

    def save(self, vault: Path) -> None:
        """Write frontmatter to the project file on disk."""
        p = project_file(vault, self.slug)
        p.parent.mkdir(parents=True, exist_ok=True)
        meta = self.to_frontmatter()
        content = self.description or ""
        post = fm.Post(content, **meta)
        atomic_write(p, dump(post))


class ProjectCreate(BaseModel):
    slug: str
    title: str
    kind: str = "project"
    tags: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    kind: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None


class Session(BaseModel):
    id: str = ""
    slug: str
    title: str
    project_slug: Optional[str] = None  # null for Home chats
    kind: str = "chat"  # chat | research
    modes: list[str] = Field(default_factory=lambda: ["text"])
    started: str = Field(default_factory=now_iso)
    ended: Optional[str] = None
    status: str = "live"  # live | closed | summarized
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    summary_pending: bool = False

    @classmethod
    def parse_filename(cls, filename: str) -> Session:
        """Parse a session filename into a Session stub."""
        m = _SESSION_FN_RE.match(filename)
        if not m:
            return cls(slug=filename.replace(".md", ""), title=filename.replace(".md", ""))
        parts = m.group(1)
        date_str, time_str, title = parts.split("-", 2)
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H%M")
        return cls(
            slug=m.group(1),
            title=title.replace("-", " ").replace("_", " "),
            started=dt.isoformat(),
        )

    def filename(self) -> str:
        """Generate the session filename."""
        title = self.title.lower().replace(" ", "-").replace("_", "-")
        # Keep it slug-like
        title = re.sub(r"[^a-z0-9\-]", "", title)[:60]
        time_str = self.started[:11].replace("-", "").replace("T", "").replace(":", "")
        return f"{time_str}-{title}.md"

    def to_frontmatter(self) -> dict:
        return {
            "id": self.id,
            "project": self.project_slug,
            "kind": self.kind,
            "title": self.title,
            "modes": self.modes,
            "started": self.started,
            "ended": self.ended,
            "status": self.status,
            "tags": self.tags,
            "summary": self.summary,
            "topics": self.topics,
            "entities": self.entities,
            "decisions": self.decisions,
            "open_questions": self.open_questions,
            "summary_pending": self.summary_pending,
        }

    @classmethod
    def from_frontmatter(cls, path: Path) -> Session:
        content = read_file(path) or ""
        post = load(content)
        meta = dict(post.metadata)
        return cls(
            id=meta.get("id", ""),
            slug=path.stem,
            title=meta.get("title", path.stem),
            project_slug=meta.get("project"),
            kind=meta.get("kind", "chat"),
            modes=meta.get("modes", ["text"]),
            started=meta.get("started", now_iso()),
            ended=meta.get("ended"),
            status=meta.get("status", "live"),
            tags=meta.get("tags", []),
            summary=meta.get("summary", ""),
            topics=meta.get("topics", []),
            entities=meta.get("entities", []),
            decisions=meta.get("decisions", []),
            open_questions=meta.get("open_questions", []),
            summary_pending=meta.get("summary_pending", False),
        )

    def _resolve_path(self, vault: Path) -> Path:
        """Determine the disk path without writing."""
        if self.project_slug:
            return session_file(vault, self.project_slug, self.filename())
        else:
            return home_session_file(vault, self.filename())

    def save(self, vault: Path) -> Path:
        """Write session to disk. Returns the path written."""
        p = self._resolve_path(vault)
        p.parent.mkdir(parents=True, exist_ok=True)
        meta = self.to_frontmatter()
        post = fm.Post(self._body or "", **meta)
        atomic_write(p, dump(post))
        return p

    def append_turn(
        self,
        vault: Path,
        role: str,
        content: str,
        mode: str = "text",
    ) -> None:
        """Append a turn to the session file body (append-only while live)."""
        path = self._resolve_path(vault)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = read_file(path) or ""
        # Split frontmatter from body
        post = load(existing)
        body = post.content
        time_str = datetime.now(timezone.utc).strftime("%H:%M")
        turn = f"\n### {role} · {time_str} · {mode}\n{content}\n"
        new_body = body.rstrip() + turn
        post.content = new_body
        atomic_write(path, dump(post))

    # Internal body cache so append_turn can preserve existing body
    _body: str = ""

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return v.lower().replace(" ", "-").replace("_", "-")


class TurnAppend(BaseModel):
    role: str  # "Keaton" or "Sunny"
    content: str
    mode: str = "text"  # text | voice


class SessionClose(BaseModel):
    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    personal_facts: list[str] = Field(default_factory=list)
