"""Vault file watcher — detects external edits and sync conflicts.

Uses watchfiles to observe the vault directory. On change:
- Tracks last-modified timestamps to defer Sunny's own writes within 60s
- Detects Syncthing conflict files (*.sync-conflict-*)
- Surfaces conflicts in admin panel and briefings
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# In-memory store: path -> last_external_edit_time
_external_edits: dict[str, float] = {}
_sync_conflicts: list[dict] = []
_watcher_thread = None
_stop_event = None


def _mark_external_edit(path: Path) -> None:
    """Record that an external process edited this path."""
    _external_edits[str(path)] = time.time()


def external_edit_since(path: Path, seconds: int = 60) -> bool:
    """Return True if the path was externally edited within the last *seconds*."""
    key = str(path)
    last = _external_edits.get(key, 0)
    return (time.time() - last) < seconds


def record_sync_conflict(conflict_path: str) -> None:
    """Record a sync conflict file."""
    _sync_conflicts.append({
        "path": conflict_path,
        "detected": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    log.warning("Sync conflict detected: %s", conflict_path)


def get_sync_conflicts() -> list[dict]:
    """Return all recorded sync conflicts."""
    return list(_sync_conflicts)


def clear_sync_conflicts() -> None:
    """Clear all recorded sync conflicts."""
    _sync_conflicts.clear()


def _scan_for_conflicts(vault: Path) -> None:
    """Scan the vault for existing sync conflict files."""
    for conflict in vault.rglob("*.sync-conflict-*"):
        record_sync_conflict(str(conflict.relative_to(vault)))


def _run_watcher(vault: Path) -> None:
    """Background watcher loop using watchfiles.

    Runs until _stop_event is set.
    """
    try:
        from watchfiles import watch, RunMode
    except ImportError:
        log.warning("watchfiles not installed; vault file watching disabled")
        return

    _scan_for_conflicts(vault)

    while not _stop_event.is_set():
        try:
            # Use a short timeout so we can check _stop_event
            changes = watch(
                vault,
                watch_count=1,
                pause=2,
                watch_filter=None,
                stop_event=_stop_event,
                raise_on_error=False,
                recurse=True,
            )
            if not changes:
                continue

            for change_type, changed_path in changes:
                p = Path(changed_path)

                # Skip .tmp files (atomic writes)
                if p.suffix == ".tmp" or ".sunny_tmp" in p.name:
                    continue

                # Skip git internal files
                if ".git" in changed_path:
                    continue

                # Detect sync conflicts
                if ".sync-conflict" in p.name:
                    record_sync_conflict(str(p.relative_to(vault)))
                    continue

                # Track external edits
                _mark_external_edit(p)

                log.debug("Vault change detected: %s", p)

        except Exception:
            log.exception("Error in vault watcher")
            # Give it a moment before retrying
            time.sleep(1)


def start_watcher(vault_path: Path) -> Optional[object]:
    """Start the vault file watcher in a background thread.

    Returns the thread, or None if watchfiles is not available.
    """
    global _watcher_thread, _stop_event

    if _watcher_thread and _watcher_thread.is_alive():
        log.debug("Vault watcher already running")
        return _watcher_thread

    _stop_event = __import__("threading").Event()
    vault_path = Path(vault_path)
    if not vault_path.exists():
        vault_path.mkdir(parents=True, exist_ok=True)

    _watcher_thread = __import__("threading").Thread(
        target=_run_watcher,
        args=(vault_path,),
        daemon=True,
        name="vault-watcher",
    )
    _watcher_thread.start()
    log.info("Vault file watcher started for %s", vault_path)
    return _watcher_thread


def stop_watcher() -> None:
    """Stop the vault file watcher."""
    global _watcher_thread
    if _stop_event:
        _stop_event.set()
    if _watcher_thread:
        _watcher_thread.join(timeout=2)
        _watcher_thread = None
    log.info("Vault file watcher stopped")
