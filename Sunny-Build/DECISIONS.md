# DECISIONS

One line each: `YYYY-MM-DD — decision — reason`.

- 2026-10-05 — Lab infra lives in `lab/`, not the repo root — keeps `docker compose` at the root pointed at Sunny's own `docker-compose.yml`.
- 2026-10-05 — All python/node/test commands run in the `sunny-sandbox` container; git runs on the host — the host OS stays clean and the sandbox never holds git credentials.
