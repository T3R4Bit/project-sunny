"""Frontmatter helpers — string-based frontmatter read/write.

The ``frontmatter`` library expects file-like objects, but we work with
strings throughout the project.  This module provides string-based helpers.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any, Optional

import frontmatter as fm


def load(text: str) -> Any:
    """Load frontmatter from a text string."""
    return fm.load(StringIO(text))


def dump(post: Any) -> str:
    """Dump a Post object to a frontmatter text string."""
    sio = StringIO()
    fm.dump(post, fd=sio)
    return sio.getvalue()


def load_file(path: Path) -> Any:
    """Load frontmatter from a file path."""
    return fm.load(path)


def dump_file(post: Any, path: Path) -> None:
    """Dump a Post object to a file path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        fm.dump(post, fd=f)
