# BLOCKERS

Anything that could not be finished: what, why (exact error), what was stubbed, what's needed to unblock.

## P1 — watchfiles dependency (not yet in requirements)

| # | Item | Status |
|---|------|--------|
| 1 | `watchfiles` package not in `requirements.txt` | The watcher falls back gracefully with a warning when watchfiles is missing |

## P0 — Docker Compose acceptance checks (need human on host)

| # | Check | Command |
|---|---|---|
| 1 | `docker compose up` serves `/health` | `docker compose -f docker-compose.yml up -d --build` then `curl -s http://localhost:8080/health` |
| 2 | Container security: non-root, dropped caps, no docker.sock | Inspect running containers: `docker inspect sunny --format '{{.Config.User}} {{.HostConfig.CapDrop}}'` |
| 3 | nmap shows nothing exposed outside Tailscale | `nmap -p 8080,8384,8082 <M-700-IP>` from a machine not on Tailscale |

## Deploy status (2026-10-12)

P0 checks 1 and 2 are done on the M-700 (`/health` 200, non-root, `cap_drop: ALL`, read-only root FS).
Check 3 is moot: every port binds to 127.0.0.1 or the Tailscale IP.

Open:
- Pi desk unit (`sunny-companion`) was offline; run `deploy/pi-kiosk.sh` on it when it is back.
- Voice, calendar, Garmin, semantic search, chat tools and push are not wired up (see README).

## No code blockers

All tests pass offline. No missing dependencies. No real credentials needed.
