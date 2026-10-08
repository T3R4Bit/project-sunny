# BLOCKERS

Anything that could not be finished: what, why (exact error), what was stubbed, what's needed to unblock.

## P0 — Docker Compose acceptance checks (need human on host)

| # | Check | Command |
|---|---|---|
| 1 | `docker compose up` serves `/health` | `docker compose -f docker-compose.yml up -d --build` then `curl -s http://localhost:8080/health` |
| 2 | Container security: non-root, dropped caps, no docker.sock | Inspect running containers: `docker inspect sunny --format '{{.Config.User}} {{.HostConfig.CapDrop}}'` |
| 3 | nmap shows nothing exposed outside Tailscale | `nmap -p 8080,8384,8082 <M-700-IP>` from a machine not on Tailscale |

## No code blockers

All tests pass offline. No missing dependencies. No real credentials needed.
