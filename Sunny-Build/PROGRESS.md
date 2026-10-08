# PROGRESS

Read `docs/spec/LAB_RUN.md` first. Update this file before ending every task.
Status values: `[ ]` todo, `[~]` in progress, `[x]` done, `[!]` partial (see BLOCKERS.md).

## Phases

Must finish:
- [x] P0 Skeleton
- [x] P1 Vault, projects, sessions
- [x] P2 Index and search
- [x] P3 Chat runtime and context system
- [x] P4 Frontend core
- [x] P5 Research
- [x] P6 Agent

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

- Phase: P7 — Extraction
- Doing: rules parser, engine, gates, audit log, starter rules with tests, hot reload
- Next: P7 implementation
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

## P3 Summary

**What was built:**
- Created `backend/sunny/router/router.py` — deterministic intent routing with confidence scoring:
  - 13 intents: list_tasks, create_task, update_task, delete_task, sleep_state, calendar_quick_add, recipe_lookup, run_agent, new_session, move_session, search, create_research, close_session
  - Confidence threshold (0.7) + margin (0.15) for execute/clarify/claude action
  - Audit log to log/routing.md
- Created `backend/sunny/llm/gateway.py` — Claude API gateway:
  - Semaphore for concurrent calls (1 awake, 2 during sleep)
  - Daily ($10) and monthly ($100) spend caps
  - Sleep sub-budget (30% of daily cap)
  - Auth latch (permanent on AuthenticationError)
  - Connection error message protection (logs type only, not message)
  - Usage logging to log/llm-usage.md
  - Streaming chat support via SSE-like async generator
  - JSON-schema mode for structured outputs
- Created `backend/sunny/llm/prompt_assembly.py` — prompt builder:
  - Assembly order: system prompt + profile + personal-context + project-context + retrieved chunks + session history + message
  - Token-budgeted sections (profile: 500, context: 1500, etc.)
  - Hot-reload from docs/instructions/<purpose>.md
  - Fallback inline prompts when files missing
- Created `backend/sunny/llm/tools.py` — chat tool registry:
  - search, list_sessions, read_session, read_context, list_projects, web_search
  - web_search gated: only callable when user explicitly asked
  - Tool specs exposed for LLM system prompt injection
- Created `backend/sunny/llm/close_hook.py` — session close automation:
  - LLM call with JSON schema for summary/topics/entities/decisions/open_questions/personal_facts
  - Writes fields into session frontmatter
  - Merges into project context.md (sections with caps)
  - Merges personal_facts into memory/personal-context.md
  - Re-indexes session, git commits
  - Falls back to summary_pending=true when LLM unavailable
- Created `backend/sunny/llm/router.py` — chat API endpoints:
  - Session CRUD (create, list, append, close) for Home and project sessions
  - Chat completion endpoint with prompt assembly
  - Streaming chat endpoint
  - Session summarize endpoint (triggers close hook)
- Updated `projects/service.py::close_session()` — integrates with LLM close hook
- Integrated LLM router into `main.py` app factory

**Test results:** 25 new tests (test_chat.py), 127 total passing

## P4 Summary

**What was built:**
- Created proper React + Vite + TypeScript frontend structure:
  - `frontend/src/main.tsx` — app entry point
  - `frontend/src/App.tsx` — main layout with page routing
  - `frontend/src/types.ts` — TypeScript types (Message, Project, Session)
  - `frontend/src/utils/api.ts` — API client for all backend endpoints
  - `frontend/src/hooks/useAuth.ts` — auth state management
  - `frontend/src/hooks/useChat.ts` — chat with streaming support
  - `frontend/src/styles/global.css` — neo-brutalist design tokens
  - `frontend/src/components/Header.tsx` — navigation bar
  - `frontend/src/pages/HomePage.tsx` — briefing page
  - `frontend/src/pages/ProjectsPage.tsx` — project list/management
  - `frontend/src/pages/SessionPage.tsx` — chat with streaming
  - `frontend/src/pages/SearchPage.tsx` — vault search UI
  - `frontend/src/pages/AdminPage.tsx` — admin shell
  - `frontend/src/pages/LoginPage.tsx` — auth login
- Added PWA manifest (`public/manifest.json`) with icons (192x192, 512x512)
- Created `tsconfig.json` and `tsconfig.node.json`
- Fixed `streaming_chat()` — removed incorrect `@asynccontextmanager` decorator
- Fixed `chat_completion_endpoint()` — made async with `await chat_completion()`
- Fixed router path for streaming endpoint (`/stream` not `/chat/stream`)
- Set streaming media type to `text/event-stream`
- Updated frontend API client paths to match backend (no `/api` prefix)

**Test results:** 20 new tests (test_frontend_api.py), 147 total passing

## P5 Summary

**What was built:**
- Created `backend/sunny/research/models.py` — research session and source models:
  - `ResearchSession` — CRUD for research sessions with goal, sources list
  - `SourceMeta` — metadata schema (title, kind, origin_url, extractor, hash, pages/duration)
  - `Source` — source with disk save (original, extracted.md, meta.yaml)
  - `SourceIngest` / `SourceIngestResult` — ingest request/result schemas
  - `sha256_hex` — content hash for deduplication
- Created `backend/sunny/research/service.py` — research service layer:
  - `create_research_session` — creates research session in vault
  - `add_source_to_research` — source ingest with dedup by content hash
  - `list_research_sources` — lists all sources in a research session
  - `_build_citation_context` — builds citation-ready context string with [S1] format
  - `_citations_replace` — converts [S1] to HTML anchor links
  - `generate_report` — generates report.md with findings, source list, open gaps
- Created `backend/sunny/research/router.py` — REST API for research:
  - GET /research — list research sessions
  - GET /research/{slug} — get research session
  - POST /research — create research session
  - GET /research/{slug}/sources — list sources
  - POST /research/{slug}/sources — ingest source
  - POST /research/{slug}/report — generate report
  - GET /research/{slug}/citations — get citation context
- Created `backend/sunny/extraction/extractors.py` — source extractors with interfaces:
  - `BaseExtractor` — abstract interface (supports, extract)
  - `TextExtractor` — plain text/markdown
  - `WebExtractor` — trafilatura for web pages
  - `PDFExtractor` — PyMuPDF with Tesseract OCR fallback
  - `YouTubeExtractor` — youtube-transcript-api with faster-whisper fallback
  - `AudioVideoExtractor` — faster-whisper for speech-to-text
  - `GitHubExtractor` — repo README via GitHub API
  - `ArXivExtractor` — arXiv XML API
  - `DocxExtractor` — python-docx
  - `ImageExtractor` — vision model stub
  - `EPUBExtractor` — ebooklib
  - `PPTXExtractor` — python-pptx
  - `XLSXExtractor` — openpyxl
  - `get_extractor(kind)` — registry lookup
- Wired research router into `sunny/main.py`
- Updated intent router: CREATE_RESEARCH intent already defined with triggers

**Test results:** 20 new tests (test_research.py), 167 total passing

## P6 Summary

**What was built:**
- Created `backend/sunny/agent/loop.py` — agent loop background task scheduler:
  - `AgentLoop` class with AWAKE/CANT_SLEEP/SLEEPING/OFF states
  - 5-minute cycle interval (300s) while Awake or Can't Sleep
  - Pull queued tasks by priority/deadline, execute, log, commit
  - Revert-on-failure: git revert to cycle-start commit on unrecoverable errors
  - Three failures → tool marked `broken`, hidden from agents
  - `start_agent_loop()` / `stop_agent_loop()` lifespan hooks
- Created `backend/sunny/tools/task_queue.py` — YAML-based task queue:
  - `TaskQueue` with enqueue, mark_running, mark_done, mark_failed
  - Tasks stored in `tasks-queue/<id>.yaml`
  - Priority sorting (1=high first), deadline-aware ordering
  - Disk persistence with atomic writes
- Created `backend/sunny/tools/registry.py` — tool registry:
  - Built-in tools: `fetch_calendar`, `create_calendar_event`, `sync_nextcloud_to_google`, `log_to_vault`, `notify`, `search`, `create_task`, `read_session`
  - Tool synthesis: writes to `tools/<name>.py`, registers in `registry.yaml`
  - Validation: names must be intention-driven (reject IDs and dates)
  - Three-failure → broken, reactivates on success
  - `TOOL_HANDLERS` dict for callable tool handlers
- Created `backend/sunny/tools/subprocess_worker.py` — tool execution isolation:
  - `execute_tool_in_subprocess(code, timeout, memory_limit_mb, tool_name)`
  - Runs tool code in a subprocess with timeout
  - JSON output parsing with error handling
  - Safe string formatting to prevent injection
- Created `backend/sunny/tools/notify.py` — proactivity tiers:
  - SILENT: Execute, log (routine work)
  - QUIET: Log + mention in next briefing (findings, background work)
  - SUGGEST: Propose, wait for approval (destructive, anticipatory)
  - ALERT: Push notification (unresolvable conflicts, tool broken ×3, git corruption)
  - `NotifyRegistry` with handler pattern
- Created `backend/sunny/tools/router.py` — agent API endpoints:
  - GET/POST /agent/status, /agent/start, /agent/stop, /agent/state
  - GET/POST /agent/tasks — task queue management
  - POST /agent/synthesize — tool synthesis with validation
  - GET /agent/tools — list all tools
- Wired agent loop into `sunny/main.py` lifespan
- Updated intent router: CREATE_RESEARCH intent already defined

**Test results:** 24 new tests (test_agent.py), 191 total passing

## P0 Blockers (need human to verify on host)

| # | Check | Command |
|---|---|---|
| 1 | `docker compose up` serves `/health` | `docker compose -f docker-compose.yml up -d --build` then `curl http://localhost:8080/health` |
| 2 | nmap shows nothing exposed outside Tailscale | `nmap -p 8080,8384,8082 <M-700-IP>` from a machine not on Tailscale |
