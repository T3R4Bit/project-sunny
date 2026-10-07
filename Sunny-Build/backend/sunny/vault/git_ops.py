"""Git operations wrapper for the vault."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def init_repo(vault_path: Path) -> None:
    """Initialize a git repo in the vault directory if not already."""
    if (vault_path / ".git").exists():
        return
    subprocess.run(
        ["git", "init"],
        cwd=str(vault_path),
        capture_output=True,
        check=True,
    )
    # Set local git config for the vault
    subprocess.run(
        ["git", "config", "user.name", "Sunny"],
        cwd=str(vault_path),
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "sunny@localhost"],
        cwd=str(vault_path),
        capture_output=True,
        check=True,
    )


def commit(vault_path: Path, message: str, files: Optional[list[str]] = None) -> Optional[str]:
    """Stage and commit changes in the vault. Returns the commit hash or None on failure."""
    cmd = ["git", "commit", "-m", message]
    if files:
        cmd.extend(files)
    else:
        cmd = ["git", "add", "-A"] + cmd

    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(vault_path),
            capture_output=True,
            check=True,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(vault_path),
            capture_output=True,
            check=True,
            timeout=30,
        )
        # Get the commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(vault_path),
            capture_output=True,
            check=True,
            text=True,
        )
        return hash_result.stdout.strip()
    except subprocess.CalledProcessError as e:
        log.error("git commit failed: %s", e.stderr.decode() if e.stderr else str(e))
        return None
    except subprocess.TimeoutExpired:
        log.error("git commit timed out")
        return None


def commit_files(vault_path: Path, message: str, file_patterns: Optional[list[str]] = None) -> Optional[str]:
    """Commit specific files or all tracked files."""
    return commit(vault_path, message, file_patterns)


def revert_to(vault_path: Path, commit_hash: str) -> bool:
    """Revert the vault to a specific commit hash. Returns True on success."""
    try:
        subprocess.run(
            ["git", "reset", "--hard", commit_hash],
            cwd=str(vault_path),
            capture_output=True,
            check=True,
            timeout=30,
        )
        return True
    except subprocess.CalledProcessError as e:
        log.error("git revert failed: %s", e.stderr.decode() if e.stderr else str(e))
        return False
    except subprocess.TimeoutExpired:
        log.error("git revert timed out")
        return False


def get_head_commit(vault_path: Path) -> Optional[str]:
    """Return the current HEAD commit hash or None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(vault_path),
            capture_output=True,
            check=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def status(vault_path: Path) -> dict:
    """Return vault git status dict: {ahead, behind, has_changes}."""
    try:
        ahead = subprocess.run(
            ["git", "rev-list", "HEAD..@{u}", "--count"],
            cwd=str(vault_path),
            capture_output=True,
            check=True,
            text=True,
        )
        behind = subprocess.run(
            ["git", "rev-list", "@{u}..HEAD", "--count"],
            cwd=str(vault_path),
            capture_output=True,
            check=True,
            text=True,
        )
        changed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(vault_path),
            capture_output=True,
            check=True,
            text=True,
        )
        return {
            "ahead": int(ahead.stdout.strip()),
            "behind": int(behind.stdout.strip()),
            "has_changes": bool(changed.stdout.strip()),
        }
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return {"ahead": 0, "behind": 0, "has_changes": False}
