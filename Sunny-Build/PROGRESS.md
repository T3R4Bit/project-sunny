# PROGRESS

Read `docs/spec/LAB_RUN.md` first. Update this file before ending every task.
Status values: `[ ]` todo, `[~]` in progress, `[x]` done, `[!]` partial (see BLOCKERS.md).

## Phases

Must finish:
- [x] P0 Skeleton
- [ ] P1 Vault, projects, sessions
- [ ] P2 Index and search
- [ ] P3 Chat runtime and context system
- [ ] P4 Frontend core

Target:
- [ ] P5 Research
- [ ] P6 Agent
- [ ] P7 Extraction
- [ ] P8 Sleep state, reports, briefing

Stretch:
- [ ] P9 Calendar
- [ ] P10 Health
- [ ] P11 Voice
- [ ] P12 Ideas and recipes
- [ ] P13 Carry-overs and migration
- [ ] P14 Hardening and deploy

## Current

- Phase: P0 ✓ complete
- Doing: nothing — P0 done
- Next: P1 Vault, projects, sessions
- Open failures: see BLOCKERS.md

## P0 Summary

**What was built:**
- Fixed `config.py` — removed Pydantic-invalid `_config_cache` / `_last_loaded` fields
- Created `.env.example` with all Settings fields as `...` placeholders
- Created `scripts/ci.sh` — installs deps, runs pytest + ruff
- Created `Dockerfile` — python:3.12-slim, non-root user
- Created `docker-compose.yml` — sunny + syncthing + nextcloud (+db) with security baseline:
  - `cap_drop: [ALL]`, `read_only: true`, `no-new-privileges`, non-root user
  - tmpfs for /tmp and .sunny
  - Shared `sunny` bridge network
- Created `backend/sunny/auth.py` — login hardening:
  - Password hash verification with sha256
  - Rate limiting: 5 attempts / 5 min lockout
  - Session cookies with `HttpOnly`, `SameSite=Strict`, `Secure`
  - Logout endpoint, auth status endpoint
  - Origin check middleware helper
- Fixed `vault/git_ops.py::status()` — split ahead/behind checks into separate try blocks so local repos without upstream tracking branch still report `has_changes` correctly
- Created `fixtures/vault/.stignore` — excludes .git, .sunny, *.tmp, .obsidian/
- Enhanced fixtures vault with missing directories: chats/, tasks-queue/, docs/instructions/, ideas-auto/, log/, memory/facts/, projects/, research/_lookups/
- Added tests: `test_auth.py` (8 tests), `test_git_ops.py` (10 tests)
- Fixed `test_fd_stability.py::test_exception_causes_rollback` — DDL auto-commits in SQLite, test now validates DML rollback

**Test results:** 43/43 passing

## P0 Blockers (need human to verify on host)

| # | Check | Command |
|---|---|---|
| 1 | `docker compose up` serves `/health` | `docker compose -f docker-compose.yml up -d --build` then `curl http://localhost:8080/health` |
| 2 | nmap shows nothing exposed outside Tailscale | `nmap -p 8080,8384,8082 <M-700-IP>` from a machine not on Tailscale |
