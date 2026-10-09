#!/usr/bin/env python3
"""Reindex the entire vault from disk.

Usage:
    python scripts/reindex.py

Drops the existing FTS5 index and rebuilds it from the vault files.
Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sunny.index.watcher import index_all_from_vault


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindex the vault from disk")
    parser.add_argument("--vault", help="Vault path (overrides .env)")
    parser.add_argument("--db", help="Database path (overrides .env)")
    args = parser.parse_args()

    from sunny.config import get_settings

    settings = get_settings()
    vault_path = Path(args.vault) if args.vault else Path(settings.vault_path)
    db_path = Path(args.db) if args.db else Path(settings.db_path)

    if not vault_path.exists():
        print(f"ERROR: Vault path {vault_path} does not exist", file=sys.stderr)
        sys.exit(1)

    count = index_all_from_vault(db_path, vault_path)
    print(f"Indexed {count} chunks from vault")


if __name__ == "__main__":
    main()
