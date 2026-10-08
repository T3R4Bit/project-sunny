"""Research session service — CRUD, source ingest, dedup, citations, reports."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sunny.config import get_settings
from sunny.extraction.extractors import get_extractor
from sunny.frontmatter import dump, load
from sunny.paths import research_dir, research_sources_dir
from sunny.research.models import (
    ResearchCreate,
    ResearchSession,
    Source,
    SourceIngest,
    SourceIngestResult,
    SourceMeta,
    sha256_hex,
)
from sunny.vault.io import read_file


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m-%d-%H%M%S")


def create_research_session(title: str, goal: str = "", project_slug: Optional[str] = None,
                            kind: str = "research") -> dict:
    """Create a new research session."""
    settings = get_settings()
    vault = Path(settings.vault_path)
    slug = f"research-{_now()}"
    session = ResearchSession(slug=slug, title=title, goal=goal, project_slug=project_slug)
    session.save(vault)

    # Also create a project-level session if project_slug is set
    if project_slug:
        from sunny.projects.service import create_session as _create_session
        proj_session = _create_session(title, project_slug=project_slug, kind=kind)
        return {"research_slug": slug, "session": proj_session.model_dump()}

    return {"research_slug": slug}


def list_research_sessions() -> list[dict]:
    """List all research sessions from the vault."""
    settings = get_settings()
    vault = Path(settings.vault_path)
    rdir = research_dir(vault, "dummy")  # won't be used since we scan vault/research/
    base = vault / "research"
    if not base.exists():
        return []
    results = []
    for d in sorted(base.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            rm = d / "research.md"
            if rm.exists():
                try:
                    session = ResearchSession.from_frontmatter(rm)
                    results.append(session.model_dump())
                except Exception:
                    results.append({"slug": d.name, "title": d.name})
    return results


def get_research_session(research_slug: str) -> ResearchSession | None:
    """Load a research session by slug."""
    settings = get_settings()
    vault = Path(settings.vault_path)
    rm = research_dir(vault, research_slug) / "research.md"
    if not rm.exists():
        return None
    return ResearchSession.from_frontmatter(rm)


def add_source_to_research(research_slug: str, ingest: SourceIngest) -> SourceIngestResult:
    """Add a source to a research session. Handles dedup."""
    settings = get_settings()
    vault = Path(settings.vault_path)

    session = get_research_session(research_slug)
    if not session:
        raise ValueError(f"Research session {research_slug} not found")

    # Extract content
    extractor = get_extractor(ingest.kind)
    if not extractor:
        raise ValueError(f"No extractor for kind: {ingest.kind}")

    content = ingest.content
    if ingest.file_data:
        content = ingest.file_data
    elif ingest.url and not ingest.content:
        content = ingest.url  # URL will be used by extractor

    result = extractor.extract(
        content=content,
        url=ingest.url,
        filename=ingest.filename,
        file_data=ingest.file_data,
    )

    source_id = f"src-{sha256_hex(ingest.kind + ingest.content + (ingest.url or ""))[:8]}"

    # Dedup check
    existing_hash = sha256_hex(result.extracted.strip())
    sources_dir = research_sources_dir(vault, research_slug)
    if sources_dir.exists():
        for src_d in sources_dir.iterdir():
            if src_d.is_dir():
                meta_path = src_d / "meta.yaml"
                if meta_path.exists():
                    meta_content = read_file(meta_path) or ""
                    meta_post = load(meta_content)
                    existing_hash_on_disk = dict(meta_post.metadata).get("hash", "")
                    if existing_hash_on_disk == existing_hash:
                        return SourceIngestResult(
                            source_id=src_d.name,
                            title=result.title,
                            added=False,
                            duplicated=True,
                        )

    # Create source
    meta = SourceMeta(
        id=source_id,
        title=result.title,
        kind=ingest.kind,
        origin_url=ingest.url,
        extractor=ingest.kind,
        hash=existing_hash,
        pages=result.pages,
        duration=result.duration,
    )
    source = Source(meta=meta, extracted_content=result.extracted, research_slug=research_slug)
    source.save(vault)

    # Update session's source list
    session.sources.append(source_id)
    session.save(vault)

    return SourceIngestResult(
        source_id=source_id,
        title=result.title,
        added=True,
        duplicated=False,
    )


def list_research_sources(research_slug: str) -> list[dict]:
    """List all sources in a research session."""
    settings = get_settings()
    vault = Path(settings.vault_path)
    sources_dir = research_sources_dir(vault, research_slug)
    if not sources_dir.exists():
        return []

    results = []
    for src_d in sorted(sources_dir.iterdir()):
        meta_path = src_d / "meta.yaml"
        if meta_path.exists():
            meta_content = read_file(meta_path) or ""
            meta_post = load(meta_content)
            meta = dict(meta_post.metadata)
            extracted = ""
            extracted_path = src_d / "extracted.md"
            if extracted_path.exists():
                extracted = extracted_path.read_text()[:500]
            results.append({
                "id": src_d.name,
                "title": meta.get("title", "Unknown"),
                "kind": meta.get("kind", "unknown"),
                "origin_url": meta.get("origin_url"),
                "extracted_preview": extracted,
            })
    return results


def _build_citation_context(session: ResearchSession) -> str:
    """Build a citation-ready context string from research sources."""
    settings = get_settings()
    vault = Path(settings.vault_path)
    sources_dir = research_sources_dir(vault, session.slug)

    if not sources_dir.exists():
        return ""

    lines = ["## Research Sources\n"]
    sources = session.sources
    for i, src_id in enumerate(sources, 1):
        src_path = sources_dir / src_id
        meta_path = src_path / "meta.yaml"
        extracted_path = src_path / "extracted.md"

        meta_content = ""
        if meta_path.exists():
            meta_content = read_file(meta_path) or ""
            meta_post = load(meta_content)
            meta = dict(meta_post.metadata)
            lines.append(f"[S{i}] {meta.get('title', src_id)} ({meta.get('kind', 'unknown')})")
            if meta.get("origin_url"):
                lines.append(f"  URL: {meta['origin_url']}")
        else:
            lines.append(f"[S{i}] {src_id}")

        extracted = ""
        if extracted_path.exists():
            extracted = read_file(extracted_path) or ""
        if extracted:
            lines.append(extracted[:2000])  # Limit size for prompt
        lines.append("")

    return "\n".join(lines)


def _citations_replace(text: str) -> str:
    """Replace bracketed citations like [S1] or [S1 §section] with HTML links."""
    def replacer(m):
        src_id = m.group(1)
        section = m.group(2) or ""
        full = m.group(0)
        link = f'<a class="citation" data-source="{src_id}" href="#source-{src_id}" title="Source {src_id}">[{full}]</a>'
        return link

    # Match [S<number>] or [S<number> §section]
    return re.sub(r'\[(S\d+)(?:\s+§([^]]+))?\]', replacer, text)


def generate_report(research_slug: str) -> str:
    """Generate report.md for a research session.

    The report contains findings, per-finding confidence, source list, and open gaps.
    This is a deterministic template; full synthesis would call the LLM.
    """
    settings = get_settings()
    vault = Path(settings.vault_path)

    session = get_research_session(research_slug)
    if not session:
        raise ValueError(f"Research session {research_slug} not found")

    sources_dir = research_sources_dir(vault, research_slug)

    findings = []
    gaps = []
    source_count = len(session.sources)

    if source_count == 0:
        gaps.append("No sources have been imported yet.")
    else:
        findings.append(f"Found {source_count} source(s) in this research session.")
        for src_id in session.sources:
            meta_path = sources_dir / src_id / "meta.yaml"
            extracted_path = sources_dir / src_id / "extracted.md"
            meta_content = ""
            if meta_path.exists():
                meta_content = read_file(meta_path) or ""
                meta_post = load(meta_content)
                meta = dict(meta_post.metadata)
            title = meta.get("title", src_id)
            kind = meta.get("kind", "unknown")
            findings.append(f"- **{title}** ({kind}): {'Content available' if extracted_path.exists() else 'No extracted content'}")

    report_content = f"""# Research Report: {session.title}

**Goal:** {session.goal or "Not specified"}
**Created:** {session.created}
**Status:** {session.status}
**Sources:** {source_count}

## Findings

{'\\n'.join(f'\\n- {f}' for f in findings) if findings else "None yet."}

## Open Gaps

{'\\n'.join(f'\\n- {g}' for g in gaps) if gaps else "No known gaps."}

## Source List

| # | Title | Kind | Extracted |
|---|-------|------|-----------|
"""
    for i, src_id in enumerate(session.sources, 1):
        meta_path = sources_dir / src_id / "meta.yaml"
        extracted_path = sources_dir / src_id / "extracted.md"
        meta_content = ""
        if meta_path.exists():
            meta_content = read_file(meta_path) or ""
            meta_post = load(meta_content)
            meta = dict(meta_post.metadata)
        title = meta.get("title", src_id)
        kind = meta.get("kind", "unknown")
        has_content = "Yes" if extracted_path.exists() else "No"
        report_content += f"| {i} | {title} | {kind} | {has_content} |\n"

    # Write report.md to disk
    rdir = research_dir(vault, research_slug)
    report_path = rdir / "report.md"
    report_path.write_text(report_content)

    return report_content
