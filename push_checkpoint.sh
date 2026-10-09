#!/usr/bin/env bash
# Commit everything and push. Runs on the HOST, from the repo root.
set -euo pipefail
cd "$(dirname "$0")"
git add -A
if git diff --cached --quiet; then
  echo "checkpoint: nothing to commit"
else
  git commit -q -m "checkpoint: $(date '+%Y-%m-%d %H:%M')"
fi
git push -q origin HEAD
echo "checkpoint: pushed $(git rev-parse --short HEAD)"
