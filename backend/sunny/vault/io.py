"""Vault atomic IO — write, merge, marker regions."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

MARKER_OPEN = "<!-- sunny:begin section={section} -->"
MARKER_CLOSE = "<!-- sunny:end section={section} -->"


def atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to *path* atomically.

    Write to a temporary file, fsync, then os.replace().  This prevents
    partial writes from corrupting synced vault files.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        suffix=".tmp",
        prefix=".sunny_tmp_",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_file(path: Path) -> str | None:
    """Read a vault file, returning None if it doesn't exist."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def file_hash(path: Path) -> str | None:
    """Return SHA-256 hex digest of a file, or None."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, PermissionError):
        return None


# --- Marker-region utilities for shared files ---


def ensure_markers(content: str, section: str) -> str:
    """Return content with a marked block for *section* if none exists.

    If a matching sunny:begin/sunny:end pair is already present, return
    content unchanged.  Otherwise append a fresh block.
    """
    open_tag = MARKER_OPEN.format(section=section)
    close_tag = MARKER_CLOSE.format(section=section)
    if open_tag in content and close_tag in content:
        return content
    block = f"\n{open_tag}\n\n{close_tag}\n"
    return content + block


def get_machine_region(content: str, section: str) -> str:
    """Return the text between sunny:begin/end markers for *section*.

    Returns empty string if markers are not found.
    """
    open_tag = MARKER_OPEN.format(section=section)
    close_tag = MARKER_CLOSE.format(section=section)
    start = content.find(open_tag)
    end = content.find(close_tag)
    if start < 0 or end < 0 or end <= start:
        return ""
    return content[start + len(open_tag) : end].strip()


def set_machine_region(content: str, section: str, new_text: str) -> str:
    """Replace the machine region for *section* with *new_text*.

    If markers don't exist, append them.
    """
    open_tag = MARKER_OPEN.format(section=section)
    close_tag = MARKER_CLOSE.format(section=section)
    start = content.find(open_tag)
    end = content.find(close_tag)
    if start < 0 or end < 0 or end <= start:
        # Append fresh block
        block = f"{open_tag}\n{new_text}\n{close_tag}\n"
        return content + "\n" + block
    before = content[: start + len(open_tag)]
    after = content[end:]
    return before + new_text + "\n" + after


def merge_shared_file(
    existing: str,
    section: str,
    new_machine_text: str,
    last_hash: Optional[str] = None,
    current_hash: Optional[str] = None,
) -> tuple[str, bool]:
    """Merge new machine content into a shared file.

    Args:
        existing: current file content.
        section: marker section name.
        new_machine_text: the new machine content to write.
        last_hash: hash when we last read this file.
        current_hash: current file hash (may be None to skip check).

    Returns:
        (merged_content, was_modified) — was_modified is False if an
        external writer changed the file since we last read it.
    """
    if last_hash is not None and current_hash is not None:
        if last_hash != current_hash:
            log.warning(
                "External edit detected on shared file while merging section '%s'; "
                "skipping write to avoid overwriting user changes",
                section,
            )
            return existing, False

    content = ensure_markers(existing, section)
    merged = set_machine_region(content, section, new_machine_text)
    return merged, True
