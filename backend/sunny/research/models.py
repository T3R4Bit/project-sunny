"""Research session models and service."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import frontmatter as fm
from pydantic import BaseModel, Field

from sunny.frontmatter import dump, load
from sunny.paths import (
    lookups_dir,
    research_dir,
    research_source_dir,
    research_sources_dir,
)
from sunny.vault.io import atomic_write, read_file


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


class SourceMeta(BaseModel):
    id: str
    title: str
    kind: str  # pdf | web | youtube | audio | video | github | arxiv | docx | pptx | xlsx | epub | image | markdown | text
    origin_url: Optional[str] = None
    imported: str = Field(default_factory=now_iso)
    extractor: str = "manual"
    hash: str = ""
    pages: Optional[int] = None
    duration: Optional[float] = None
    notes: str = ""


class Source(BaseModel):
    meta: SourceMeta
    extracted_content: str = ""
    research_slug: str

    def save(self, vault: Path) -> None:
        """Write source to disk: original, extracted.md, meta.yaml."""
        src_dir = research_source_dir(vault, self.research_slug, self.meta.id)
        src_dir.mkdir(parents=True, exist_ok=True)
        # Write original content
        original_path = src_dir / "original"
        original_path.write_text(self.meta.kind + "\n" + self.extracted_content)
        # Write extracted.md
        extracted_path = src_dir / "extracted.md"
        extracted_path.write_text(self.extracted_content)
        # Write meta.yaml
        meta_path = src_dir / "meta.yaml"
        meta_post = fm.Post("", **self.meta.model_dump())
        atomic_write(meta_path, dump(meta_post))

    @classmethod
    def from_file(cls, vault: Path, research_slug: str, source_id: str) -> Source | None:
        src_dir = research_source_dir(vault, research_slug, source_id)
        meta_path = src_dir / "meta.yaml"
        if not meta_path.exists():
            return None
        content = read_file(meta_path) or ""
        post = load(content)
        meta = SourceMeta(**{k: v for k, v in dict(post.metadata).items() if k in SourceMeta.model_fields()})
        extracted = ""
        extracted_path = src_dir / "extracted.md"
        if extracted_path.exists():
            extracted = extracted_path.read_text()
        return cls(meta=meta, extracted_content=extracted, research_slug=research_slug)

    def dedup_hash(self) -> str:
        content = self.extracted_content.strip()
        return sha256_hex(content)


class ResearchSession(BaseModel):
    slug: str
    title: str
    goal: str = ""
    project_slug: Optional[str] = None
    sources: list[str] = Field(default_factory=list)  # source IDs
    status: str = "live"  # live | closed
    created: str = Field(default_factory=now_iso)
    ended: Optional[str] = None
    summary: str = ""

    def to_frontmatter(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "goal": self.goal,
            "project": self.project_slug,
            "sources": self.sources,
            "status": self.status,
            "created": self.created,
            "ended": self.ended,
            "summary": self.summary,
        }

    @classmethod
    def from_frontmatter(cls, path: Path) -> ResearchSession:
        content = read_file(path) or ""
        post = load(content)
        meta = dict(post.metadata)
        return cls(
            slug=meta.get("slug", path.stem),
            title=meta.get("title", path.stem.replace("-", " ").title()),
            goal=meta.get("goal", ""),
            project_slug=meta.get("project"),
            sources=meta.get("sources", []),
            status=meta.get("status", "live"),
            created=meta.get("created", now_iso()),
            ended=meta.get("ended"),
            summary=meta.get("summary", ""),
        )

    def save(self, vault: Path) -> Path:
        rdir = research_dir(vault, self.slug)
        rdir.mkdir(parents=True, exist_ok=True)
        p = rdir / "research.md"
        meta = self.to_frontmatter()
        post = fm.Post("", **meta)
        atomic_write(p, dump(post))
        return p


class ResearchCreate(BaseModel):
    title: str
    goal: str = ""
    project_slug: Optional[str] = None


class SourceIngest(BaseModel):
    kind: str
    content: str = ""
    url: Optional[str] = None
    filename: Optional[str] = None
    file_data: Optional[str] = None  # base64-encoded binary data


class SourceIngestResult(BaseModel):
    source_id: str
    title: str
    added: bool  # whether it was a new source
    duplicated: bool  # whether it was skipped due to dedup
