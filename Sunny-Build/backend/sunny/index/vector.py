"""Vector search stub — semantic search backend.

This module provides a pluggable semantic search interface. The real
implementation uses `fastembed` + `sqlite-vec`, but since those packages
may not install on aarch64, we default to a no-op stub that always
returns empty results.

The stub can be replaced by importing the real implementation:

    from sunny.index import vector
    vector.enable()

See enable_vector_backend() below.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

log = logging.getLogger(__name__)


@dataclass
class VectorHit:
    """A semantic search result."""
    path: str
    snippet: str
    score: float  # cosine similarity 0-1
    project: str | None = None
    kind: str = "file"
    session_id: str | None = None
    source_id: str | None = None
    tags: list[str] = field(default_factory=list)


# Internal state
_backend: Optional[Callable] = None
_enabled = False


def set_backend(fn: Callable) -> None:
    """Register a vector search backend function.

    The backend must accept (query, filters) and return a list of VectorHit.
    """
    global _backend, _enabled
    _backend = fn
    _enabled = True
    log.info("Vector search backend enabled")


def is_enabled() -> bool:
    return _enabled


def search_vector(
    query: str,
    *,
    project: Optional[str] = None,
    kinds: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    k: int = 8,
) -> list[VectorHit]:
    """Run a semantic search query.

    Returns empty list when the backend is not available (default).
    """
    if _backend is None:
        return []
    return _backend(query, project=project, kinds=kinds, tags=tags, k=k)


def try_enable() -> bool:
    """Attempt to enable the real vector backend. Returns True on success."""
    try:
        _do_enable_real()
        return True
    except Exception as e:
        log.warning("Could not enable vector search (fastembed/sqlite-vec): %s", e)
        return False


def _do_enable_real() -> None:
    """Real backend that wires up fastembed + sqlite-vec."""
    import json
    import sqlite3
    from pathlib import Path

    from sunny.config import get_settings

    settings = get_settings()
    db_path = settings.db_path

    # Load sqlite-vec
    try:
        import sqlite_vec  # type: ignore
    except ImportError:
        raise ImportError("sqlite-vec package not installed (needed for vector search)")

    conn = sqlite3.connect(str(db_path))
    sqlite_vec.load(conn)
    conn.execute("PRAGMA journal_mode=WAL")

    # Create vector table
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec
        USING vec0(embedding float[])
    """)

    # Get fastembed
    try:
        from fastembed import TextEmbedding  # type: ignore
    except ImportError:
        conn.close()
        raise ImportError("fastembed package not installed (needed for vector search)")

    model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    def _search(query: str, *, project, kinds, tags, k: int) -> list[VectorHit]:
        # Embed the query
        query_embedding = list(model.query_embed_text(query))[0]
        embedding_str = json.dumps(query_embedding)

        filters = []
        params = []
        if project:
            filters.append("c.project = ?")
            params.append(project)
        if kinds:
            ph = ",".join("?" for _ in kinds)
            filters.append(f"c.kind IN ({ph})")
            params.extend(kinds)

        where = ""
        if filters:
            where = "WHERE " + " AND ".join(filters)

        rows = conn.execute(f"""
            SELECT c.path, c.project, c.kind, c.session_id, c.tags,
                   v.distance
            FROM chunks_vec v
            JOIN chunks_meta c ON v.rowid = c.rowid
            {where}
            ORDER BY v.distance
            LIMIT ?
        """, params + [k]).fetchall()

        hits = []
        for row in rows:
            path, project, kind, session_id, tags_json, distance = row
            hits.append(VectorHit(
                path=path,
                snippet="",
                score=1.0 - distance,  # distance is 1-similarity
                project=project,
                kind=kind,
                session_id=session_id,
                tags=json.loads(tags_json) if tags_json else [],
            ))
        return hits

    set_backend(_search)
    conn.close()
