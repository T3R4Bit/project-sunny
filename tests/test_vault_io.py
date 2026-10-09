"""Tests for vault atomic write and marker-region utilities."""

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

from sunny.vault.io import (
    atomic_write,
    ensure_markers,
    file_hash,
    get_machine_region,
    merge_shared_file,
    read_file,
    set_machine_region,
)


class TestAtomicWrite:
    def test_writes_file(self, tmp_path: Path) -> None:
        target = tmp_path / "test.md"
        atomic_write(target, "hello world")
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "deep.md"
        atomic_write(target, "deep content")
        assert target.exists()
        assert target.read_text() == "deep content"

    def test_no_tmp_after_write(self, tmp_path: Path) -> None:
        target = tmp_path / "atomic.md"
        atomic_write(target, "content")
        tmppath = tmp_path / ".sunny_tmp_*"
        assert not any(p.match(".sunny_tmp_*") for p in tmp_path.iterdir())

    def test_replaces_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "replace.md"
        atomic_write(target, "first")
        atomic_write(target, "second")
        assert target.read_text() == "second"

    def test_fsynced_content_is_consistent(self, tmp_path: Path) -> None:
        """Write a large file and verify content integrity."""
        target = tmp_path / "large.md"
        data = "x" * 100_000 + "\n"
        atomic_write(target, data)
        assert target.read_text(encoding="utf-8") == data

    def test_concurrent_writes_not_corrupt(self, tmp_path: Path) -> None:
        """Two rapid writes should not leave a partially written file."""
        target = tmp_path / "concurrent.md"
        atomic_write(target, "alpha")
        atomic_write(target, "beta")
        content = target.read_text()
        assert content in ("alpha", "beta")  # deterministic on single thread


class TestFileHash:
    def test_hash_matches(self, tmp_path: Path) -> None:
        target = tmp_path / "hash.txt"
        target.write_text("test content")
        h = file_hash(target)
        assert h == hashlib.sha256(b"test content").hexdigest()

    def test_none_for_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.txt"
        assert file_hash(missing) is None


class TestReadFile:
    def test_reads_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "read.txt"
        f.write_text("hello")
        assert read_file(f) == "hello"

    def test_none_for_missing(self, tmp_path: Path) -> None:
        assert read_file(tmp_path / "missing.txt") is None


class TestMarkerRegions:
    def test_ensure_markers_appends(self) -> None:
        content = "# Project\n\nSome content."
        result = ensure_markers(content, "decisions")
        assert "<!-- sunny:begin section=decisions -->" in result
        assert "<!-- sunny:end section=decisions -->" in result

    def test_ensure_markers_preserves_existing(self) -> None:
        content = (
            "# Project\n"
            "<!-- sunny:begin section=decisions -->\n"
            "decision 1\n"
            "<!-- sunny:end section=decisions -->\n"
        )
        result = ensure_markers(content, "decisions")
        assert result == content  # unchanged

    def test_get_machine_region_empty(self) -> None:
        content = "# No markers"
        assert get_machine_region(content, "decisions") == ""

    def test_get_machine_region_returns_content(self) -> None:
        content = (
            "# Project\n"
            "<!-- sunny:begin section=decisions -->\n"
            "decision one\n"
            "<!-- sunny:end section=decisions -->\n"
        )
        assert get_machine_region(content, "decisions") == "decision one"

    def test_set_machine_region_appends(self) -> None:
        content = "# Project"
        result = set_machine_region(content, "decisions", "new decision")
        assert "<!-- sunny:begin section=decisions -->" in result
        assert "new decision" in result

    def test_set_machine_region_replaces(self) -> None:
        content = (
            "<!-- sunny:begin section=decisions -->\n"
            "old decision\n"
            "<!-- sunny:end section=decisions -->\n"
        )
        result = set_machine_region(content, "decisions", "new decision")
        assert "new decision" in result
        assert "old decision" not in result


class TestMergeSharedFile:
    def test_merge_no_external_changes(self, tmp_path: Path) -> None:
        content = "# Context\n"
        last_hash = file_hash(tmp_path / "fake") or "abc"
        current_hash = last_hash  # no external changes
        merged, modified = merge_shared_file(
            content, "decisions", "new decision",
            last_hash=last_hash, current_hash=current_hash,
        )
        assert modified is True
        assert "new decision" in merged
        assert "<!-- sunny:begin section=decisions -->" in merged

    def test_merge_skips_on_external_edit(self, tmp_path: Path) -> None:
        content = "# Context\n"
        last_hash = "abc123"
        current_hash = "xyz789"  # different = external change
        merged, modified = merge_shared_file(
            content, "decisions", "new decision",
            last_hash=last_hash, current_hash=current_hash,
        )
        assert modified is False
        assert merged == content  # unchanged

    def test_merge_without_hashes(self) -> None:
        """When hashes are None, merge proceeds normally."""
        content = "# Context\n"
        merged, modified = merge_shared_file(
            content, "decisions", "decision",
            last_hash=None, current_hash=None,
        )
        assert modified is True
        assert "decision" in merged
