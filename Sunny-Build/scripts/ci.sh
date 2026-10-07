#!/usr/bin/env bash
# CI script — runs tests and lint checks.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Installing backend ==="
pip install -e backend/ >/dev/null 2>&1
pip install -e "backend/[dev]" >/dev/null 2>&1

echo "=== Running tests ==="
python -m pytest tests/ -v

echo "=== Linting ==="
ruff check backend/sunny/

echo "=== All checks passed ==="
