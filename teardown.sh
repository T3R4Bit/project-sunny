#!/usr/bin/env bash
# End-of-week teardown on the lab DGX. Pushes everything, then removes credentials and containers.
set -uo pipefail
cd "$(dirname "$0")"

echo "== Final checkpoint"
if ! ./push_checkpoint.sh; then
  echo "PUSH FAILED. Fix this before tearing down, or the work is lost when the disk is wiped."
  exit 1
fi
echo "Latest commit on origin: $(git rev-parse --short HEAD). Confirm it on GitHub before leaving."

echo "== Stopping lab containers"
(cd lab && docker compose down)

echo "== Removing git credentials and identity"
git credential-cache exit 2>/dev/null || true
rm -f "$HOME/.gitconfig" "$HOME/.git-credentials"

cat <<'EOF'

Manual, required:
  1. GitHub > Settings > Developer settings > Fine-grained tokens > delete the lab token.
  2. Sign out of GitHub in the DGX browser.
EOF
