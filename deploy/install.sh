#!/usr/bin/env bash
# Deploy or update Sunny V2 on the M-700. Run from the repo root as the `sunny` user:
#   git pull && deploy/install.sh
# Safe to re-run. Needs: docker + compose plugin, passwordless sudo, Tailscale with HTTPS certs.
# Never touches the Minecraft user units.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"

[ -f .env ] || { echo ".env missing: copy .env.example to .env and fill it in" >&2; exit 1; }
chmod 600 .env

echo "== host status collector (feeds the Dashboard page)"
sudo mkdir -p /home/sunny/sunny-status && sudo chown sunny:sunny /home/sunny/sunny-status
sudo tee /etc/systemd/system/sunny-collector.service >/dev/null <<EOF
[Unit]
Description=Sunny dashboard host status collector
After=docker.service tailscaled.service

[Service]
ExecStart=/usr/bin/python3 $REPO/deploy/collector.py
Restart=always
RestartSec=10
Nice=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable sunny-collector.service
sudo systemctl restart sunny-collector.service

echo "== build + start"
sudo docker compose up -d --build --remove-orphans

echo "== wait for health"
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:8080/health && echo

echo "== publish over Tailscale HTTPS (tailnet only)"
sudo tailscale serve --bg --https=443 http://127.0.0.1:8080 >/dev/null
# Port 5443 only exists because the Google OAuth client's registered redirect URI uses it
sudo tailscale serve --bg --https=5443 http://127.0.0.1:8080 >/dev/null
sudo tailscale serve status

echo "== nightly backup timer"
sudo tee /etc/systemd/system/sunny-backup.service >/dev/null <<EOF
[Unit]
Description=Sunny vault + database backup
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
ExecStart=$REPO/deploy/backup.sh
ExecStartPost=/bin/chown -R sunny:sunny /home/sunny/sunny-backups
EOF
sudo tee /etc/systemd/system/sunny-backup.timer >/dev/null <<'EOF'
[Unit]
Description=Nightly Sunny backup

[Timer]
OnCalendar=*-*-* 04:30:00
Persistent=true
RandomizedDelaySec=10m

[Install]
WantedBy=timers.target
EOF
chmod +x deploy/backup.sh
sudo systemctl daemon-reload
sudo systemctl enable --now sunny-backup.timer
systemctl list-timers sunny-backup.timer --no-pager | head -3

echo "== done: https://$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
