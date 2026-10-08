"""Index watcher — reindexes vault files when the file watcher detects changes."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from pathlib import Path

from sunny.config import get_settings
from sunny.index.chunker import chunk_text, chunk_session_file, chunk_source_file
from sunny.index.service import index_chunk

log = logging.getLogger(__name__)

# Debounce: skip reindex if the same file changes within this many seconds
_DEBOUNCE_WINDOW = 2.0
_debounce: dict[str, float] = {}
_watcher_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


async def start_index_watcher() -> None:
    """Start the background index watcher task."""
    global _watcher_task, _stop_event
    if _watcher_task and not _watcher_task.done():
        log.debug("Index watcher already running")
        return
    _stop_event = asyncio.Event()
    _watcher_task = asyncio.create_task(_watch_loop())


async def stop_index_watcher() -> None:
    """Stop the background index watcher task."""
    global _watcher_task, _stop_event
    if _stop_event:
        _stop_event.set()
    if _watcher_task:
        _watcher_task.cancel()
        try:
            await _watcher_task
        except asyncio.CancelledError:
            pass
        _watcher_task = None


def _needs_reindex(path: str) -> bool:
    """Check if we should reindex this path (debounce)."""
    now = time.time()
    last = _debounce.get(path, 0)
    if now - last < _DEBOUNCE_WINDOW:
        return False
    _debounce[path] = now
    return True


def _classify_path(path: str) -> tuple[str, str | None, str | None]:
    """Classify a vault path and return (kind, session_id, source_id)."""
    # sessions/
    parts = path.split("/")
    for i, part in enumerate(parts):
        if part == "sessions" and i + 1 < len(parts):
            return "session", parts[i + 1].replace(".md", ""), None
        if part == "sources" and i + 1 < len(parts):
            source_id = parts[i + 1]
            if "extracted.md" in parts[i + 2] if i + 2 < len(parts) else False:
                return "source", None, source_id
    return "file", None, None


def _reindex_path(db_path: Path, vault_path: Path, file_path: Path) -> int:
    """Reindex a single file. Returns the number of chunks indexed."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        log.warning("Cannot read file for indexing: %s", file_path)
        return 0

    rel_path = str(file_path.relative_to(vault_path))
    conn = sqlite3.connect(str(db_path))
    try:
        kind, session_id, source_id = _classify_path(rel_path)

        if kind == "session":
            chunks = chunk_session_file(content, rel_path, project=None)
        elif kind == "source":
            chunks = chunk_source_file(content, source_id or "unknown")
        else:
            chunks = chunk_text(content, rel_path)

        for chunk in chunks:
            index_chunk(conn, chunk)
        conn.commit()
        return len(chunks)
    except Exception:
        conn.rollback()
        log.exception("Failed to reindex %s", file_path)
        return 0
    finally:
        conn.close()


async def _watch_loop() -> None:
    """Background loop watching the vault for file changes."""
    settings = get_settings()
    vault_path = Path(settings.vault_path)
    db_path = Path(settings.db_path)

    if not vault_path.exists():
        log.warning("Vault path %s does not exist; index watcher waiting", vault_path)
        await asyncio.sleep(5)
        if not _stop_event.is_set():
            await _watch_loop()
        return

    log.info("Index watcher started for %s", vault_path)

    # Initial index of existing files
    await _initial_index(db_path, vault_path)

    # Poll the vault directory for changes
    while not _stop_event.is_set():
        await asyncio.sleep(2)
        try:
            await _poll_changes(db_path, vault_path)
        except Exception:
            log.exception("Error in index watcher poll")


async def _initial_index(db_path: Path, vault_path: Path) -> int:
    """Index all existing vault files. Returns total chunks indexed."""
    total = 0
    log.info("Running initial index of %s", vault_path)
    for md in vault_path.rglob("*.md"):
        if ".git" in str(md):
            continue
        if ".tmp" in str(md):
            continue
        count = _reindex_path(db_path, vault_path, md)
        total += count
    log.info("Initial index complete: %d chunks", total)
    return total


async def _poll_changes(db_path: Path, vault_path: Path) -> None:
    """Poll for new/changed files and reindex them."""
    count = 0
    for md in vault_path.rglob("*.md"):
        if ".git" in str(md):
            continue
        if ".tmp" in str(md):
            continue
        if _needs_reindex(str(md)):
            result = _reindex_path(db_path, vault_path, md)
            count += result
    if count:
        log.debug("Reindexed %d chunks from vault changes", count)


def index_all_from_vault(db_path: Path, vault_path: Path) -> int:
    """Synchronously reindex all vault files. Used by reindex script.

    Returns total chunks indexed.
    """
    total = 0
    log.info("Full reindex from vault: %s", vault_path)
    for md in vault_path.rglob("*.md"):
        if ".git" in str(md):
            continue
        if ".tmp" in str(md):
            continue
        count = _reindex_path(db_path, vault_path, md)
        total += count
    log.info("Reindex complete: %d chunks", total)
    return total
