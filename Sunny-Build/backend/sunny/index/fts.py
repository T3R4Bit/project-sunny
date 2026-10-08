"""FTS5 keyword search — lightweight full-text indexing over vault files.

SQLite FTS5 provides BM25 scoring with no external dependencies.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class Hit:
    """A single search result."""
    path: str
    snippet: str = ""
    score: float = 0.0  # BM25 score from FTS5
    rank: int = 0
    project: str | None = None
    kind: str = "file"
    session_id: str | None = None
    source_id: str | None = None
    tags: list[str] = field(default_factory=list)
    mode: str = "text"


def init_fts(db_path: Path) -> None:
    """Create the FTS5 table and associated metadata table."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(text, content='chunks_meta', content_rowid='rowid')
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks_meta (
                rowid INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                project TEXT,
                kind TEXT NOT NULL DEFAULT 'file',
                session_id TEXT,
                source_id TEXT,
                turn_range_start INTEGER,
                turn_range_end INTEGER,
                tags TEXT,
                mode TEXT DEFAULT 'text'
            )
        """)
        conn.commit()
    finally:
        conn.close()


def add_chunk(conn: sqlite3.Connection, chunk) -> None:
    """Insert or update a chunk in the FTS index.

    *chunk* is a Chunk dataclass instance.
    """
    tags_json = json.dumps(chunk.tags)
    turn_start = chunk.turn_range[0] if chunk.turn_range else None
    turn_end = chunk.turn_range[1] if chunk.turn_range else None

    conn.execute("""
        INSERT OR REPLACE INTO chunks_meta
            (rowid, path, project, kind, session_id, source_id,
             turn_range_start, turn_range_end, tags, mode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        id(chunk), chunk.path, chunk.project, chunk.kind,
        chunk.session_id, chunk.source_id,
        turn_start, turn_end, tags_json, chunk.mode,
    ))

    conn.execute("""
        INSERT OR REPLACE INTO chunks_fts (rowid, text)
        VALUES (?, ?)
    """, (id(chunk), chunk.text))


def remove_chunk(conn: sqlite3.Connection, chunk_id: int) -> None:
    """Remove a chunk from the FTS index."""
    conn.execute("DELETE FROM chunks_fts WHERE rowid = ?", (chunk_id,))
    conn.execute("DELETE FROM chunks_meta WHERE rowid = ?", (chunk_id,))


def search_fts(
    conn: sqlite3.Connection,
    query: str,
    *,
    project: Optional[str] = None,
    kinds: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    since: Optional[str] = None,
    k: int = 8,
) -> list[Hit]:
    """Run an FTS5 keyword search using bm25() scoring.

    Returns Hit instances sorted by BM25 score descending.
    Tags are filtered post-search since json_each requires a special JOIN
    that conflicts with the FTS5 MATCH syntax.
    """
    # Build filter conditions to append after MATCH (use AND)
    conditions: list[str] = []
    params: list = [query]

    if project:
        conditions.append("c.project = ?")
        params.append(project)
    if kinds:
        placeholders = ",".join("?" for _ in kinds)
        conditions.append(f"c.kind IN ({placeholders})")
        params.extend(kinds)
    if since:
        conditions.append("c.path >= ?")
        params.append(since)

    where_clause = ""
    if conditions:
        where_clause = " AND " + " AND ".join(conditions)

    query_sql = f"""
        SELECT c.path, c.project, c.kind, c.session_id,
               c.source_id, c.tags, c.mode,
               bm25(chunks_fts) as score
        FROM chunks_fts
        JOIN chunks_meta c ON chunks_fts.rowid = c.rowid
        WHERE chunks_fts MATCH ?{where_clause}
        ORDER BY bm25(chunks_fts)
        LIMIT ?
    """
    params.append(k)

    rows = conn.execute(query_sql, params).fetchall()

    # Post-filter by tags (can't easily combine with MATCH)
    if tags:
        filtered = []
        for row in rows:
            tags_json = row[5]
            row_tags = json.loads(tags_json) if tags_json else []
            if any(t in row_tags for t in tags):
                filtered.append(row)
        rows = filtered

    hits = []
    for i, row in enumerate(rows):
        path, project, kind, session_id, source_id, tags_json, mode, score = row
        hits.append(Hit(
            path=path,
            score=abs(score) if score else 0.0,
            rank=i,
            project=project,
            kind=kind,
            session_id=session_id,
            source_id=source_id,
            tags=json.loads(tags_json) if tags_json else [],
            mode=mode,
        ))
    return hits
