#!/usr/bin/env bash
# Turn the Raspberry Pi desk unit into a full-screen Sunny display.
# Run on the Pi as the `sunny` user (needs sudo):   bash pi-kiosk.sh [URL]
#
# Uses cage (a single-app Wayland compositor) + Chromium on tty1, so it works on Raspberry Pi OS
# Lite and Desktop alike. The Pi must be on the tailnet (it is: `sunny-companion`).
# Log in once with a USB keyboard; sessions renew while in use, so it stays logged in.
# Undo: sudo systemctl disable --now sunny-kiosk && sudo rm /etc/systemd/system/sunny-kiosk.service
set -euo pipefail

URL="${1:-https://sunshine-m700.wahoo-sidewinder.ts.net/}"
USER_NAME="$(id -un)"

echo "== packages"
sudo apt-get update -qq
CHROMIUM=chromium
apt-cache show chromium >/dev/null 2>&1 || CHROMIUM=chromium-browser
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cage "$CHROMIUM" fonts-noto-color-emoji >/dev/null

echo "== stop the old v1 face service (code is left in place)"
systemctl --user disable --now sunny-face.service 2>/dev/null || true

echo "== kiosk service on tty1"
sudo systemctl disable --now getty@tty1.service 2>/dev/null || true
sudo tee /etc/systemd/system/sunny-kiosk.service >/dev/null <<EOF
[Unit]
Description=Sunny kiosk (cage + Chromium)
After=systemd-user-sessions.service network-online.target tailscaled.service
Wants=network-online.target
Conflicts=getty@tty1.service

[Service]
User=$USER_NAME
PAMName=login
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=journal
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u)
ExecStartPre=/bin/sh -c 'until tailscale status >/dev/null 2>&1; do sleep 2; done'
ExecStart=/usr/bin/cage -d -s -- /usr/bin/$CHROMIUM --kiosk --noerrdialogs --disable-infobars \\
  --no-first-run --check-for-update-interval=31536000 --overscroll-history-navigation=0 \\
  --ozone-platform=wayland --app=$URL
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now sunny-kiosk.service
echo "== done: Sunny should appear on the Pi's screen. Plug in a keyboard once to log in."
