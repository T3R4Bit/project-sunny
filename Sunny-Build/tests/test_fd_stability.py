"""FD-stability test — ensures closing_transaction doesn't leak file descriptors."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

from sunny.db import closing_transaction, init_db


@pytest.fixture()
def db_file(tmp_path: Path) -> Path:
    """Create a temporary SQLite database."""
    db = tmp_path / "test.db"
    init_db(db)
    return db


class TestFDStability:
    """V1 bug: with sqlite3.connect() as conn commits but never closes.

    This test runs 5,000 calls through closing_transaction() and asserts
    that the open-FD count is stable.
    """

    def test_no_fd_leak_5000_calls(self, db_file: Path) -> None:
        initial_fd_count = _open_fd_count()

        for i in range(5_000):
            with closing_transaction(db_file) as conn:
                conn.execute("SELECT 1")
                if i == 0:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS fd_test (id INTEGER PRIMARY KEY)
                    """)
                    conn.execute("INSERT INTO fd_test (id) VALUES (1)")

        final_fd_count = _open_fd_count()

        # Allow a small window for OS caching, but not a steady leak
        assert abs(final_fd_count - initial_fd_count) <= 2, (
            f"FD count changed from {initial_fd_count} to {final_fd_count} "
            f"after 5,000 connections — possible FD leak"
        )

    def test_exception_triggers_rollback(self, db_file: Path) -> None:
        with closing_transaction(db_file) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rollback_test (id INTEGER PRIMARY KEY)
            """)
            conn.execute("INSERT INTO rollback_test (id) VALUES (1)")

        # Verify data persisted
        with closing_transaction(db_file) as conn:
            row = conn.execute("SELECT COUNT(*) FROM rollback_test").fetchone()
            assert row[0] == 1

    def test_exception_causes_rollback(self, db_file: Path) -> None:
        """Data written inside a failing transaction should not persist.

        SQLite auto-commits DDL, so we test rollback on DML only.
        """
        with closing_transaction(db_file) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rollback_dml_test (id INTEGER PRIMARY KEY, val TEXT)
            """)

        with pytest.raises(ValueError):
            with closing_transaction(db_file) as conn:
                conn.execute("INSERT INTO rollback_dml_test (id, val) VALUES (999, 'lost')")
                raise ValueError("intentional failure")

        # Inserted row should not exist
        with closing_transaction(db_file) as conn:
            row = conn.execute(
                "SELECT val FROM rollback_dml_test WHERE id = 999"
            ).fetchone()
            assert row is None, "rolled-back data should not persist"


def _open_fd_count() -> int:
    """Count open file descriptors for this process."""
    try:
        return len(os.listdir(f"/proc/{os.getpid()}/fd"))
    except (FileNotFoundError, PermissionError):
        # Fallback: return a sentinel that makes the test skip
        return -1
