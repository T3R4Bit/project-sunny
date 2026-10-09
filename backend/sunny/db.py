"""DB helpers — closing_transaction() and pooled read connections."""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

_lock = threading.Lock()


def _ensure_db(db_path: Path) -> None:
    """Create DB file and directories, enable WAL mode."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _init_tables(conn)
    conn.close()


def _init_tables(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            project TEXT,
            kind TEXT NOT NULL,
            session_id TEXT,
            source_id TEXT,
            turn_range TEXT,
            created TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            mode TEXT DEFAULT 'text',
            content TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
            USING fts5(content, path, project, kind, tags);

        CREATE TABLE IF NOT EXISTS embeddings (
            id TEXT PRIMARY KEY,
            chunk_id TEXT NOT NULL REFERENCES chunks(id),
            vector BLOB NOT NULL,
            created TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            created TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            priority INTEGER NOT NULL DEFAULT 4,
            deadline TEXT,
            agent TEXT NOT NULL DEFAULT 'default',
            source TEXT NOT NULL DEFAULT 'user',
            description TEXT NOT NULL,
            result TEXT
        );

        CREATE TABLE IF NOT EXISTS llm_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            purpose TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost REAL NOT NULL,
            latency_ms REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            project_slug TEXT,
            status TEXT NOT NULL DEFAULT 'live',
            metadata TEXT DEFAULT '{}',
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'project',
            status TEXT NOT NULL DEFAULT 'active',
            metadata TEXT DEFAULT '{}',
            created TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_kind ON chunks(kind);
        CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
        CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_slug);
    """)


@contextmanager
def closing_transaction(db_path: Path = Path(".sunny/sunny.db")) -> Iterator[sqlite3.Connection]:
    """Open a connection, auto-rollback on any exception.

    V1 bug: connections were never closed (FD leak). This context manager
    guarantees closure.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_read_connection(db_path: Path = Path(".sunny/sunny.db")) -> sqlite3.Connection:
    """Return a long-lived pooled read connection (one per thread).

    Used for hot read paths; write path always uses closing_transaction().
    """
    thread_id = threading.get_ident()
    with _lock:
        if not hasattr(get_read_connection, "_pools"):
            get_read_connection._pools = {}  # type: ignore
        pool = get_read_connection._pools  # type: ignore
        if thread_id not in pool:
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA query_only=ON")
            pool[thread_id] = conn
        return pool[thread_id]


def init_db(db_path: Path | None = None) -> None:
    """Initialize the database file and tables."""
    path = db_path or Path(".sunny/sunny.db")
    _ensure_db(path)
