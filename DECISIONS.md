# DECISIONS

One line each: `YYYY-MM-DD — decision — reason`.

- 2026-10-05 — Lab infra lives in `lab/`, not the repo root — keeps `docker compose` at the root pointed at Sunny's own `docker-compose.yml`.
- 2026-10-05 — All python/node/test commands run in the `sunny-sandbox` container; git runs on the host — the host OS stays clean and the sandbox never holds git credentials.
- 2026-10-07 — Login accepts any non-empty password when `ADMIN_PASSWORD_HASH` is empty (P0 scaffolding) — allows tests to run without real credentials, gates on auth configured
- 2026-10-07 — `vault/git_ops.py::status()` handles missing upstream gracefully — local-only vault repos have no upstream branch; split ahead/behind into separate try blocks
- 2026-10-07 — Auth module uses in-memory session store for P0 — real session backend (Redis/DB) comes in a later phase when persistence is needed
- 2026-10-07 — Docker Compose security baseline: `cap_drop: [ALL]`, `read_only: true`, non-root user — per SUNNY_V2_SECURITY §A, ships with P0 at zero ongoing cost
- 2026-10-08 — Frontmatter uses string-based helpers (sunny/frontmatter.py) — the frontmatter library expects file-like objects; wrapping load/dump avoids passing bytes/strings interchangeably and prevents API misuse
- 2026-10-08 — Session body is append-only on disk while live — save() overwrites but append_turn reads-then-writes to preserve prior turns; _resolve_path separates path computation from writing
- 2026-10-08 — Context.md uses custom marker regions (§5.6), not frontmatter — frontmatter is only for project.md and session files; shared files use <!-- sunny:begin/end --> markers for external-edit-safe merging
