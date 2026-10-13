#!/usr/bin/env bash
# Nightly Sunny backup: vault git bundle (full history) + SQLite online backup + LLM spend file.
# Writes ~/sunny-backups/sunny-<UTC timestamp>.tar.gz and keeps the newest $KEEP archives.
# Installed as the root systemd timer sunny-backup.timer by deploy/install.sh.
set -euo pipefail

DEST="${SUNNY_BACKUP_DIR:-/home/sunny/sunny-backups}"
KEEP="${SUNNY_BACKUP_KEEP:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="/tmp/sunny-backup-$STAMP"   # /tmp inside the container is a tmpfs

mkdir -p "$DEST"

# Archive is streamed out on stdout (docker cp cannot read the container's tmpfs /tmp)
OUT="$DEST/sunny-$STAMP.tar.gz"
trap 'rm -f "$OUT.part"' ERR
docker exec sunny sh -c "
  set -e
  mkdir -p $WORK
  exec 3>&1 1>&2   # keep stdout clean for the archive
  if [ -d /data/sunny-vault/.git ]; then
    git -C /data/sunny-vault add -A || true
    git -C /data/sunny-vault commit -q -m 'backup: snapshot before nightly bundle' || true
    git -C /data/sunny-vault bundle create $WORK/vault.bundle --all
  fi
  python -c \"import sqlite3; s=sqlite3.connect('/app/.sunny/sunny.db'); d=sqlite3.connect('$WORK/sunny.db'); s.backup(d); d.close(); s.close()\"
  cp /app/.sunny/llm-spend.json $WORK/ 2>/dev/null || true
  tar -czf - -C $WORK . >&3
  rm -rf $WORK
" > "$OUT.part"
mv "$OUT.part" "$OUT"

# Retention
ls -1t "$DEST"/sunny-*.tar.gz | tail -n +"$((KEEP + 1))" | xargs -r rm -f
echo "backup written: $OUT ($(du -h "$OUT" | cut -f1))"

# Restore:
#   tar -xzf sunny-<stamp>.tar.gz -C /tmp/restore
#   git clone /tmp/restore/vault.bundle /tmp/restore/vault   # full vault with history
#   sunny.db is a consistent SQLite copy (drop into the sunny-state volume as /app/.sunny/sunny.db)
