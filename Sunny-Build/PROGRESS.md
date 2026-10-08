# PROGRESS

Read `docs/spec/LAB_RUN.md` first. Update this file before ending every task.
Status values: `[ ]` todo, `[~]` in progress, `[x]` done, `[!]` partial (see BLOCKERS.md).

## Phases

Must finish:
- [x] P0 Skeleton
- [x] P1 Vault, projects, sessions
- [x] P2 Index and search
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

- Phase: P3 — Chat runtime and context system
- Doing: building router, gateway, prompt assembly, session close hook
- Next: P3 acceptance checks
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

## P1 Summary

**What was built:**
- Created `backend/sunny/paths.py` — canonical vault path layout with helpers for project, session, context, research, facts, logs, etc.
- Created `backend/sunny/projects/models.py` — Project and Session Pydantic models with frontmatter serialization:
  - Project: CRUD, status transitions (active/archive), tags, kind classification
  - Session: filename parsing, turn appending, close with summary/topics/entities/decisions
  - Frontmatter: load/dump using string-based helpers (frontmatter.py wrapper)
- Created `backend/sunny/projects/service.py` — business logic:
  - Project CRUD + context section management (8 sections with caps)
  - Session CRUD + append turns + close with context merge
  - Session move between projects or Home
  - Personal fact merging, sync conflict detection integration
- Created `backend/sunny/projects/router.py` — FastAPI routes:
  - `/projects` CRUD, `/projects/{slug}/context` update
  - `/projects/{slug}/sessions` CRUD + append/close/move
  - `/chats/sessions` (Home) CRUD + append/close
  - `/sync/conflicts` admin endpoints
- Created `backend/sunny/watcher.py` — vault file watcher:
  - Uses watchfiles to detect external edits
  - Tracks external edit timestamps (60s defer window)
  - Detects Syncthing conflict files (*.sync-conflict-*)
  - Runs in background daemon thread
- Created `backend/sunny/frontmatter.py` — string-based frontmatter helpers:
  - `load(text)` / `dump(post)` for string content
  - `load_file(path)` / `dump_file(post, path)` for file paths
- Integrated watcher into `main.py` lifespan
- Fixed `fm.post.Post` → `fm.Post(content, **metadata)` API usage
- Added `Project.description` field

**Test results:** 78/78 passing (35 new in test_projects.py)

## P2 Summary

**What was built:**
- Created `backend/sunny/index/chunker.py` — text chunker that splits by markdown headings and fixed-size windows with configurable overlap
- Created `backend/sunny/index/fts.py` — FTS5 keyword search with BM25 scoring, project/kind/since filters, post-search tag filtering
- Created `backend/sunny/index/vector.py` — vector search backend stub (fastembed + sqlite-vec), auto-disables if packages unavailable
- Created `backend/sunny/index/service.py` — unified search service with hybrid RRF (reciprocal rank fusion) merging of keyword + semantic hits
- Created `backend/sunny/index/watcher.py` — background index watcher that reindexes changed vault files with 2s debounce, plus `index_all_from_vault()` for reindex scripts
- Created `backend/sunny/index/router.py` — `/search` API endpoint supporting mode=hybrid|keyword|semantic, project/kind/tags/since filters
- Integrated index watcher into `main.py` lifespan (starts with app, stops on shutdown)
- Created `scripts/reindex.py` — drops and rebuilds the entire index from disk, idempotent
- Fixed FTS5 search: uses `bm25()` function for scoring; WHERE conditions appended via AND after MATCH clause to avoid syntax errors
- Tags filtered post-search since json_each JOIN conflicts with FTS5 MATCH

**Test results:** 24 new tests (test_index.py), 102 total passing

## P0 Blockers (need human to verify on host)

| # | Check | Command |
|---|---|---|
| 1 | `docker compose up` serves `/health` | `docker compose -f docker-compose.yml up -d --build` then `curl http://localhost:8080/health` |
| 2 | nmap shows nothing exposed outside Tailscale | `nmap -p 8080,8384,8082 <M-700-IP>` from a machine not on Tailscale |
