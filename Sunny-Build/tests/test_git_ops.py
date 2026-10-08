"""Tests for vault git operations."""

from pathlib import Path

import pytest

from sunny.vault.git_ops import (
    commit,
    get_head_commit,
    init_repo,
    revert_to,
    status,
)


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a git repo for testing."""
    init_repo(tmp_path)
    return tmp_path


class TestInitRepo:
    def test_init_creates_git_dir(self, tmp_path: Path) -> None:
        init_repo(tmp_path)
        assert (tmp_path / ".git").exists()

    def test_init_is_idempotent(self, tmp_path: Path) -> None:
        init_repo(tmp_path)
        init_repo(tmp_path)
        assert (tmp_path / ".git").exists()


class TestCommit:
    def test_commit_succeeds(self, git_repo: Path) -> None:
        test_file = git_repo / "test.md"
        test_file.write_text("hello")

        hash_val = commit(git_repo, "test commit")
        assert hash_val is not None
        assert len(hash_val) == 40  # git SHA is 40 hex chars

    def test_commit_with_specific_files(self, git_repo: Path) -> None:
        file1 = git_repo / "a.md"
        file2 = git_repo / "b.md"
        file1.write_text("a")
        file2.write_text("b")

        hash_val = commit(git_repo, "commit files", ["a.md", "b.md"])
        assert hash_val is not None

    def test_commit_fails_outside_repo(self, tmp_path: Path) -> None:
        # tmp_path is not a git repo
        result = commit(tmp_path, "should fail")
        assert result is None


class TestRevert:
    def test_revert_to_commit(self, git_repo: Path) -> None:
        # Create initial commit
        f = git_repo / "file.txt"
        f.write_text("v1")
        hash1 = commit(git_repo, "v1")

        # Change and commit again
        f.write_text("v2")
        hash2 = commit(git_repo, "v2")

        # Revert to hash1
        assert revert_to(git_repo, hash1) is True
        assert f.read_text() == "v1"

    def test_revert_to_bad_hash(self, git_repo: Path) -> None:
        assert revert_to(git_repo, "abcdef1234567890") is False


class TestGetHeadCommit:
    def test_head_commit_returns_none_before_init(self, tmp_path: Path) -> None:
        assert get_head_commit(tmp_path) is None

    def test_head_commit_returns_hash_after_commit(self, git_repo: Path) -> None:
        (git_repo / "x.txt").write_text("x")
        commit(git_repo, "x")
        h = get_head_commit(git_repo)
        assert h is not None
        assert len(h) == 40


class TestStatus:
    def test_status_no_changes(self, git_repo: Path) -> None:
        (git_repo / "empty.txt").write_text("")
        commit(git_repo, "init")
        s = status(git_repo)
        assert s["has_changes"] is False
        assert s["ahead"] == 0
        assert s["behind"] == 0

    def test_status_has_changes(self, git_repo: Path) -> None:
        (git_repo / "new.txt").write_text("new")
        s = status(git_repo)
        assert s["has_changes"] is True
