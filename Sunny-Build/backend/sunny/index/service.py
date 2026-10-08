"""Index service — orchestrates chunking, indexing, and hybrid search.

Ties together the chunker, FTS5 keyword search, and vector (semantic) search
to provide a unified search API with hybrid RRF (reciprocal rank fusion).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from sunny.index.chunker import Chunk, chunk_text
from sunny.index.fts import (
    Hit,
    add_chunk as _fts_add,
    init_fts,
    remove_chunk,
    search_fts as _search_fts,
)
from sunny.index.vector import VectorHit, is_enabled, search_vector

log = logging.getLogger(__name__)

# RRF constant
RRF_K = 60


@dataclass
class SearchResult:
    """A merged search result combining keyword and semantic hits."""
    path: str
    snippet: str
    rank: int
    fts_score: float = 0.0
    vec_score: float = 0.0
    rrf_score: float = 0.0
    project: str | None = None
    kind: str = "file"
    session_id: str | None = None
    source_id: str | None = None
    tags: list[str] = field(default_factory=list)
    mode: str = "text"


def init_index(db_path: Path) -> None:
    """Initialize all index tables in the database."""
    init_fts(db_path)
    # Try to enable vector search (no-op if fastembed/sqlite-vec unavailable)
    from sunny.index.vector import try_enable
    try_enable()


def index_chunk(conn: sqlite3.Connection, chunk: Chunk) -> None:
    """Index a single chunk in the database."""
    _fts_add(conn, chunk)
    # Vector indexing is handled by a separate periodic job
    # since embedding is expensive and doesn't block search


def index_text(
    conn: sqlite3.Connection,
    text: str,
    path: str,
    *,
    project: Optional[str] = None,
    kind: str = "file",
    session_id: Optional[str] = None,
    source_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> list[int]:
    """Index a text blob, returning the list of chunk rowids."""
    chunks = chunk_text(text, path, chunk_size=400, overlap=60)
    chunk_ids: list[int] = []
    for chunk in chunks:
        chunk.project = project
        chunk.kind = kind
        chunk.session_id = session_id
        chunk.source_id = source_id
        if tags:
            chunk.tags = tags
        conn.execute("BEGIN")
        _fts_add(conn, chunk)
        chunk_ids.append(id(chunk))
        conn.commit()
    return chunk_ids


def remove_indexed(
    conn: sqlite3.Connection,
    chunk_ids: list[int],
) -> None:
    """Remove indexed chunks from the index."""
    for chunk_id in chunk_ids:
        remove_chunk(conn, chunk_id)


def search(
    query: str,
    *,
    project: Optional[str] = None,
    kinds: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    since: Optional[date] = None,
    mode: str = "hybrid",
    k: int = 8,
) -> list[SearchResult]:
    """Unified search with three modes.

    Args:
        query: Search text.
        project: Filter by project slug (None = everything).
        kinds: Filter by chunk kind (session, source, context, etc.).
        tags: Filter by tag (multiple = AND).
        since: Filter by path >= this date string.
        mode: "hybrid", "keyword", or "semantic".
        k: Max results to return.

    Returns:
        SearchResult instances sorted by relevance.
    """
    # Get keyword hits from FTS5
    keyword_hits: list[Hit] = []
    if mode in ("hybrid", "keyword"):
        try:
            from sunny.config import get_settings
            settings = get_settings()
            db_path = settings.db_path
            conn = sqlite3.connect(str(db_path))
            try:
                keyword_hits = _search_fts(
                    conn, query,
                    project=project,
                    kinds=kinds,
                    tags=tags,
                    since=since.isoformat() if since else None,
                    k=k * 3,  # over-fetch for RRF merging
                )
            finally:
                conn.close()
        except Exception:
            log.exception("FTS5 search failed")

    # Get semantic hits (may be empty if vector backend unavailable)
    semantic_hits: list[VectorHit] = []
    if mode in ("hybrid", "semantic") and is_enabled():
        try:
            semantic_hits = search_vector(
                query,
                project=project,
                kinds=kinds,
                tags=tags,
                k=k * 3,
            )
        except Exception:
            log.exception("Vector search failed")

    if mode == "keyword" and keyword_hits:
        return _hits_to_results(keyword_hits)
    if mode == "semantic" and semantic_hits:
        return _vector_hits_to_results(semantic_hits)

    # Hybrid RRF
    return _rrf_merge(keyword_hits, semantic_hits, k)


def _hits_to_results(hits: list[Hit]) -> list[SearchResult]:
    """Convert FTS Hit objects to SearchResult objects."""
    results: list[SearchResult] = []
    for i, h in enumerate(hits):
        results.append(SearchResult(
            path=h.path,
            snippet=h.snippet,
            rank=i,
            fts_score=h.score,
            project=h.project,
            kind=h.kind,
            session_id=h.session_id,
            source_id=h.source_id,
            tags=h.tags,
            mode=h.mode,
        ))
    return results


def _vector_hits_to_results(hits: list[VectorHit]) -> list[SearchResult]:
    """Convert VectorHit objects to SearchResult objects."""
    results: list[SearchResult] = []
    for i, h in enumerate(hits):
        results.append(SearchResult(
            path=h.path,
            snippet=h.snippet,
            rank=i,
            vec_score=h.score,
            project=h.project,
            kind=h.kind,
            session_id=h.session_id,
            tags=h.tags,
        ))
    return results


def _rrf_merge(
    keyword_hits: list[Hit],
    semantic_hits: list[VectorHit],
    k: int,
) -> list[SearchResult]:
    """Merge keyword and semantic hits using Reciprocal Rank Fusion.

    RRF score = sum over sources of 1 / (k + rank),
    where k is a constant (default 60) and rank is 0-based.
    """
    score_map: dict[str, list[float]] = {}

    for i, h in enumerate(keyword_hits):
        key = h.path
        if key not in score_map:
            score_map[key] = [0.0, 0.0]  # [fts, vec]
        score_map[key][0] += 1.0 / (RRF_K + i)

    for i, h in enumerate(semantic_hits):
        key = h.path
        if key not in score_map:
            score_map[key] = [0.0, 0.0]
        score_map[key][1] += 1.0 / (RRF_K + i)

    # Build merged results
    merged: list[SearchResult] = []
    for path, (fts_score, vec_score) in score_map.items():
        rrf = fts_score + vec_score
        # Find hit data for metadata
        fts_hit = next((h for h in keyword_hits if h.path == path), None)
        vec_hit = next((h for h in semantic_hits if h.path == path), None)

        merged.append(SearchResult(
            path=path,
            snippet=fts_hit.snippet if fts_hit else (vec_hit.snippet if vec_hit else ""),
            rank=0,  # filled in below
            fts_score=fts_score,
            vec_score=vec_score,
            rrf_score=rrf,
            project=fts_hit.project if fts_hit else (vec_hit.project if vec_hit else None),
            kind=fts_hit.kind if fts_hit else (vec_hit.kind if vec_hit else "file"),
            session_id=fts_hit.session_id if fts_hit else (vec_hit.session_id if vec_hit else None),
            source_id=fts_hit.source_id if fts_hit else (vec_hit.source_id if vec_hit else None),
            tags=fts_hit.tags if fts_hit else (vec_hit.tags if vec_hit else []),
            mode=fts_hit.mode if fts_hit else "text",
        ))

    merged.sort(key=lambda r: r.rrf_score, reverse=True)
    for i, r in enumerate(merged[:k]):
        r.rank = i
    return merged[:k]
