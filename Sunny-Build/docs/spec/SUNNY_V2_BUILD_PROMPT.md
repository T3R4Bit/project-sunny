# SUNNY V2 — COMPLETE BUILD PROMPT

You are the sole engineer building **Sunny V2**, a single-user, self-hosted personal AI assistant, from an empty repository to a deployable system. This document is your entire specification. Read all of it before writing any code. Work autonomously through every phase in §24. Do not stop to ask questions: when something is ambiguous, pick the option most consistent with this document, record it in `DECISIONS.md` (one line: date, decision, reason), and keep going.

---

## 0. How you work

1. **Phases in order.** Build §24's phases sequentially. A phase is done only when its acceptance checks pass. Commit at the end of each phase: `phase N: <name>`.
2. **Keep three files current at repo root:**
   - `PROGRESS.md` — phase checklist, what's done, what's next.
   - `DECISIONS.md` — every judgment call you make that this spec didn't dictate.
   - `BLOCKERS.md` — anything you could not finish (missing credential, unreachable service, library bug). Stub the interface, write a failing-with-clear-message placeholder, log it here, move on. Never silently skip.
3. **Tests are not optional.** Every module gets pytest coverage for its core behavior. External services (Claude, Nextcloud, Google, Garmin, OpenWeatherMap, Spotify, research APIs) are hidden behind interfaces with a fake implementation used in tests. The full test suite must pass offline.
4. **No real secrets exist on this machine and none should be requested.** Build against `.env.example` placeholders and fakes. See §23.
5. **Build the thing that's specified, not a generic assistant.** If you catch yourself producing boilerplate that could belong to any project (generic dashboard cards, stock gradients, "Welcome back! 👋"), stop and re-read §20 and §21.
6. **Prefer boring, legible code.** Plain functions and small classes, type hints everywhere, docstrings that state *why*, not *what*. No framework you don't need.

---

## 1. What Sunny is

Sunny is Keaton's personal assistant: a FastAPI backend + a web/PWA frontend, running 24/7 on his homelab server (the **M-700**, TrueNAS SCALE, Docker, reachable over Tailscale). It talks to Claude for reasoning, keeps everything it knows as markdown files in a folder that is **live-synced bidirectionally with Keaton's PC**, and runs a background agent that works while he's awake and does heavier batch work while he sleeps.

Keaton is a full-time student (BBA, Entrepreneurship & Management, KSU), FSAE engineering member, homelab builder, and video producer. He ships MVPs fast, owns his infrastructure, refuses paid cloud services where a self-hosted option exists, and has zero tolerance for generic AI-looking output.

The core capabilities, in priority order:

1. **Projects and sessions** — Claude-style chats (text or voice) that live inside projects. Every chat updates a per-project context file and a separate personal context file. Full transcripts are always kept and searchable.
2. **Research** — NotebookLM-style research sessions with imported sources, created only on explicit request, with cited answers.
3. **Agent** — task queue, tool synthesis, git-backed safety, 5-minute cycles.
4. **Sleep state** — Awake / Sleeping / Can't Sleep, with batch work overnight and a morning briefing.
5. **Supporting systems** — extraction rules, calendar (Nextcloud primary, Google mirror), Garmin health, idea refinement, reports dashboard, recipes, voice.

---

## 2. Non-negotiables

- **Single user.** No multi-tenant abstractions, no user table beyond what auth needs.
- **Self-hosted and free**, except the Claude API itself. No paid SaaS, no paid search APIs, no hosted vector DBs.
- **Markdown is the source of truth** for everything human-meaningful. SQLite holds only indexes, caches, time series, and operational state — anything in SQLite that describes vault content must be rebuildable from the vault with one command.
- **One router, one Claude gateway.** Every interface (web chat, voice, API) goes through `router.handle(message, ctx)` and every Claude call goes through `llm/gateway.py`. This is V1's best architectural property; preserve it.
- **Fail quiet at integrations, loud in logs.** Integration calls return `None`/`False` on failure, never raise into the router. Every failure is logged with enough context to debug.
- **Git is the safety net** for the vault and synthesized tools. No permission gates. Every agent write is committed; every failure can be reverted.
- **Personality is JARVIS/Muse** (§21). No emoji, no enthusiasm, no filler, anywhere — UI copy, briefings, chat, logs.

---

## 3. Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.12, FastAPI, uvicorn | Single process + isolated child processes where noted |
| Scheduling | Own asyncio loops with a double-start guard | Lifespan-hook startup (V1 lesson: must work under every launch form) |
| DB | SQLite, WAL mode | `.sunny/sunny.db`; never synced |
| Keyword search | SQLite FTS5 (BM25) | |
| Semantic search | `sqlite-vec` + `fastembed` (ONNX, `BAAI/bge-small-en-v1.5`) | No torch. CPU-only. |
| Git | `git` CLI via subprocess | Wrapped in `vault/git_ops.py` |
| Sync | Syncthing (Docker) | Live, bidirectional, PC ↔ M-700 |
| Calendar | Nextcloud (Docker) via `caldav` | Google Calendar = one-way mirror |
| STT | `faster-whisper` (int8, CPU) for final transcripts; Vosk for live partials | See §10 |
| TTS | Piper | Local |
| VAD | Silero VAD (ONNX) | |
| Frontend | React + Vite + TypeScript, built to static, served by FastAPI | Installable PWA; mobile-first |
| Deploy | Docker Compose | Target: M-700 / TrueNAS SCALE apps or plain compose |

Claude models are configured in `.env`, never hardcoded in logic:

```
SUNNY_MODEL_FAST=claude-haiku-4-5-20251001
SUNNY_MODEL_DEFAULT=claude-sonnet-5-5
SUNNY_MODEL_DEEP=claude-opus-5-5
```

Use FAST for routing assists, titles, and short summaries; DEFAULT for chat and structured extraction; DEEP only for sleep-mode deep review, research synthesis, and idea attack cycles.

---

## 4. Repository layout

```
sunny/
├── PROGRESS.md  DECISIONS.md  BLOCKERS.md  README.md
├── docker-compose.yml          # sunny, syncthing, nextcloud (+ its db)
├── .env.example
├── backend/
│   ├── sunny/
│   │   ├── main.py             # app factory, lifespan, loop registry
│   │   ├── config.py           # pydantic settings, 5s TTL live reload, looks_configured()
│   │   ├── router/             # deterministic intents + confidence scoring + audit log
│   │   ├── llm/                # gateway, spend caps, prompt assembly, streaming
│   │   ├── vault/              # atomic IO, frontmatter, paths, git_ops, file ownership
│   │   ├── projects/           # projects, sessions, context files
│   │   ├── research/           # research sessions, source ingest, pathfinder
│   │   ├── index/              # chunker, FTS5, vectors, hybrid search, watcher, reindex
│   │   ├── agent/              # loop, task queue, tool registry, synthesis, sandbox
│   │   ├── extraction/         # markdown rules engine
│   │   ├── sleep/              # state machine, batch jobs, sleep report
│   │   ├── calendar/           # caldav client, google mirror
│   │   ├── health/             # garmin ingest, readiness, narrative
│   │   ├── ideas/              # refinement loop, auto-ideation
│   │   ├── reports/            # report builders, timeline, export
│   │   ├── briefing/           # morning / evening templates
│   │   ├── recipes/
│   │   ├── voice/              # ws endpoint, stt/tts workers (child process)
│   │   ├── notify/             # web push + in-app channel registry
│   │   ├── carryover/          # ported V1 modules (see §22)
│   │   └── db.py               # closing_transaction(), pooled read conns
│   └── tests/
├── frontend/
├── scripts/                    # reindex, migrate_v1, restart, backup
└── fixtures/vault/             # synthetic vault used by tests — no real data
```

---

## 5. The synced vault

### 5.1 Layout

The vault root (`SUNNY_VAULT_PATH`, default `/data/sunny-vault`) is an Obsidian-compatible folder synced live with Keaton's PC by Syncthing.

```
sunny-vault/
├── .stignore                   # MUST exclude .git, .sunny, *.tmp, .obsidian/workspace*
├── projects/
│   └── <project-slug>/
│       ├── project.md          # frontmatter metadata + human description
│       ├── context.md          # rolling project context (§7)
│       ├── sessions/
│       │   └── 2026-09-29-1402-aero-package-tradeoffs.md
│       ├── research/
│       │   └── <research-slug>/   # same shape as global research (§9)
│       └── files/              # anything Keaton drops in; indexed, never auto-edited
├── research/                   # research not tied to a project
│   └── <research-slug>/
│       ├── research.md         # frontmatter + goal
│       ├── sources/<source-id>/{original.*, extracted.md, meta.yaml}
│       ├── sessions/           # research chats
│       └── report.md           # latest synthesis
├── chats/                      # sessions started outside any project ("Home")
├── memory/
│   ├── profile.md              # HUMAN-OWNED. Sunny never writes.
│   ├── personal-context.md     # rolling personal context (§7)
│   └── facts/                  # extracted facts, one dated file per day, by tier
├── tasks-queue/                # agent task YAMLs
├── tools/                      # synthesized tools (.py) + registry.yaml
├── ideas/  ideas-auto/
├── recipes/
├── reports/{action,research,health,ideas,sleep}/
├── docs/
│   ├── instructions/           # system prompts by purpose, hot-reloaded
│   ├── personality.md          # HUMAN-OWNED dials
│   └── extraction-rules.md
└── log/                        # routing.md, extraction.md, llm-usage.md, agent.md, sync.md
```

The vault is a git repo **on the server only**. `.git` must never sync (syncing a git directory between two live machines corrupts it). Keaton's PC sees the files; history lives on the M-700.

### 5.2 File ownership

Every file is exactly one of:

- **Human-owned** (`profile.md`, `personality.md`, anything under `files/`, `project.md` body): Sunny reads, never writes.
- **Machine-owned** (session files while a session is live, `tasks-queue/`, `reports/`, `log/`, `tools/`): Sunny writes freely.
- **Shared** (`context.md`, `personal-context.md`, `extraction-rules.md`, ideas): Sunny writes only inside marked regions:

```markdown
<!-- sunny:begin section=decisions -->
...machine content...
<!-- sunny:end section=decisions -->
```

Anything outside markers is Keaton's and is preserved byte-for-byte. If markers are missing or malformed, Sunny appends a fresh marked block at the end and logs a warning — it never rewrites the human part to "repair" it.

### 5.3 Write discipline and sync conflicts

- All writes go through `vault/io.py::atomic_write(path, text)` → write `.tmp` sibling, fsync, `os.replace`.
- Before writing a shared file, compare its mtime/hash to the last value Sunny read. If Keaton changed it since, re-read, re-merge the machine section only, then write. Never overwrite an external edit.
- A file watcher (`watchfiles`) observes the vault. If a shared file was modified by a non-Sunny writer within the last 60 seconds, defer Sunny's write to the next cycle (Keaton is probably mid-edit).
- Syncthing conflict files (`*.sync-conflict-*`) are detected by the watcher, surfaced in the admin panel and the next briefing, and never deleted automatically.
- Every agent write batch ends in a git commit with a descriptive message (`context: aero-package — 2 decisions, 1 open question`).

### 5.4 Frontmatter schemas

`project.md`:
```yaml
id: prj_01J...            # ULID
slug: fsae-aero
title: FSAE Aero Package
kind: project             # project | research
status: active            # active | long_term | someday | archived
tags: [fsae, cad, aero]
created: 2026-09-29T14:02:00-04:00
```

Session file:
```yaml
id: ses_01J...
project: fsae-aero        # or null for Home chats
kind: chat                # chat | research
title: Aero package tradeoffs   # auto-generated, editable
modes: [text, voice]      # a session can mix both
started: ...
ended: ...                # null while live
status: live              # live | closed | summarized
tags: [...]
summary: >                # written at close (§6.3)
topics: [...]
entities: [...]
decisions: [...]
open_questions: [...]
```

Body: one heading per turn, append-only while live.

```markdown
### Keaton · 14:02 · voice
Text of the turn.

### Sunny · 14:02
Reply. Citations like [S3 §2] link to sources.
```

---

## 6. Projects and sessions

### 6.1 Behavior

- Keaton can create as many projects and sessions as he wants, like Claude's own projects. A session belongs to exactly one project, or to **Home** (`chats/`) if started outside one.
- A session can move between projects (file moves, frontmatter updates, index updates, git commit).
- Titles: auto-generated by FAST model after the second exchange; editable any time. Tags editable any time.
- Text and voice are the same session type. A single session may contain both; each turn records its mode.
- The live session is appended turn by turn so a crash loses at most one turn.

### 6.2 Session lifecycle

`live` → `closed` (explicit close, or 30 minutes idle) → `summarized` (close hook runs §6.3).

### 6.3 Close hook (runs on every session close)

One DEFAULT-model call with a JSON schema produces: `summary` (≤120 words), `topics`, `entities`, `decisions`, `open_questions`, `personal_facts` (things about Keaton rather than the project). Then:

1. Write those fields into the session frontmatter.
2. Merge project-relevant items into the project's `context.md` (§7.1).
3. Merge personal items into `memory/personal-context.md` (§7.2).
4. Run extraction rules (§13) over the transcript.
5. Re-index the session.
6. Git commit.

If the call fails or the spend cap blocks it, mark the session `closed` with `summary_pending: true`; the sleep cycle retries.

---

## 7. The context system

Modeled on how Claude's project memory works: every chat feeds one project context file and one personal context file, and those are what future chats start from.

### 7.1 `projects/<slug>/context.md`

Machine sections, each capped:

| Section | Content | Cap |
|---|---|---|
| `state` | Current state of the project in a short paragraph | 150 words |
| `decisions` | Dated decisions with a link to the session that made them | 30 items |
| `open_questions` | Unresolved questions, removed when answered | 20 items |
| `entities` | People, parts, tools, concepts that matter here | 40 items |
| `sources` | Research and sources in play, linked | 20 items |
| `recent_sessions` | Last 10 sessions: date, title, one line, link | 10 items |
| `history` | Compressed older state | 300 words |

When a section exceeds its cap, overflow goes to `history`, compressed by the sleep cycle. The whole machine region should stay under ~2,000 tokens.

### 7.2 `memory/personal-context.md`

Same mechanism, sections: `current_focus`, `preferences`, `goals`, `constraints`, `people`, `running_references` (jokes, abbreviations, self-references — the tier-3 personality memory). `profile.md` remains human-owned and is always loaded ahead of it.

### 7.3 Update cadence

- **Per session close:** incremental merge (§6.3).
- **Sleep cycle:** consolidation pass per project touched that day — dedupe, resolve answered questions, compress history, check every link still resolves.

---

## 8. Index and search

### 8.1 What's indexed

Sessions (chunked by turn groups, ~400 tokens, 60-token overlap), context files, extracted source text, project files, ideas, reports, recipes, facts. Each chunk row carries metadata: `path, project, kind, session_id, source_id, turn_range, created, tags, mode`.

### 8.2 Three search modes, one API

```python
search(query: str,
       project: str | None = None,     # None = everything
       kinds: list[str] | None = None, # session, source, context, file, idea, ...
       tags: list[str] | None = None,
       since: date | None = None,
       mode: Literal["hybrid","keyword","semantic"] = "hybrid",
       k: int = 8) -> list[Hit]
```

Hybrid = FTS5 BM25 + vector cosine, merged with reciprocal rank fusion, then metadata filters. Each `Hit` includes the snippet, path, and a stable anchor so the UI and the model can jump to the exact turn or source section.

### 8.3 Freshness

- The watcher re-indexes changed files within seconds (debounced 2s), including Keaton's edits from the PC.
- `scripts/reindex.py` drops and rebuilds the whole index from disk. It must be idempotent and must be the documented recovery path.

---

## 9. Research

### 9.1 Creation rule

A research session is created **only** when Keaton explicitly asks ("start research on X", the New Research button, or voice). Sources are imported **only**:

- inside a research session, or
- in a normal chat when Keaton explicitly says to look something up. In that case Sunny searches, answers, and saves what it used as sources on the current project (`research/_lookups/`), with provenance.

Sunny never browses or imports on its own initiative in chat. (Sleep-mode deep research is separate — §14 — and only runs on topics Keaton queued.)

### 9.2 Source ingest

Import via drag-and-drop, paste (URL or text), or chat/voice command inside a research session. Each source gets `sources/<id>/` with the original, `extracted.md`, and `meta.yaml` (`title, kind, origin_url, imported, extractor, hash, pages/duration, notes`).

| Kind | Extractor |
|---|---|
| PDF | PyMuPDF text layer; if a page has no text, OCR with Tesseract via `ocrmypdf` |
| Web page | `trafilatura` |
| YouTube | `youtube-transcript-api`; fall back to downloading audio + faster-whisper |
| Audio / video file | faster-whisper |
| GitHub repo | shallow clone → README, tree, selected source files |
| arXiv ID / DOI | arXiv API / Crossref → PDF path above |
| DOCX, PPTX, XLSX, EPUB | python-docx, python-pptx, openpyxl, ebooklib |
| Images | Claude vision description + any OCR text |
| Markdown / text | as-is |

Deduplicate by content hash. Ingest runs in a worker so a slow extraction never blocks chat.

### 9.3 Research chat

Research sessions work like NotebookLM: answers are grounded in the session's sources first, retrieved via `search(..., kinds=["source"])` scoped to that research folder. Every claim drawn from a source carries a citation `[S<n> §<section>]` that the UI renders as a link to the exact passage. When the sources don't cover something, Sunny says so plainly and offers to look it up (which, if accepted, imports the new source).

`report.md` is regenerated on request or at session close: findings, per-finding confidence, source list, open gaps.

### 9.4 Pathfinder (deep research)

Used when Keaton asks for a deep dive or queues a topic for sleep mode. Pipeline: plan (sub-questions) → multi-query search → fetch → extract → cross-reference → follow breadcrumbs (citations, linked repos, archived versions) → synthesize → `report.md` with a source audit (queries run, sources hit, confidence per finding, contradictions).

Free sources to wire, each behind an interface with a fake:

- Claude web search tool (counts against the spend cap)
- arXiv API, OpenAlex, Semantic Scholar, Crossref
- GitHub search API (unauthenticated, rate-limited)
- Hacker News (Algolia API), Reddit public JSON
- Wayback Machine CDX
- World Bank API, NOAA
- Kaggle only if a key is configured

Google Scholar has no API and actively blocks scraping. Do not scrape it; OpenAlex and Semantic Scholar cover the same need.

---

## 10. Voice

- Browser captures mic via AudioWorklet → 16 kHz mono PCM → WebSocket `/ws/voice`.
- Modes: push-to-talk (default) and always-listening with Silero VAD. No wake word.
- Server side: Vosk streams live partial transcripts to the UI; on utterance end, faster-whisper produces the final transcript that goes to the router and into the session file (Vosk alone is too inaccurate for permanent transcripts). Claude does not accept audio input, so there is no Claude transcription fallback.
- Replies stream sentence by sentence from the gateway to Piper and back as audio chunks, so speech starts before the reply is finished.
- The whole audio pipeline runs in an **isolated child process** (`multiprocessing`) with a supervisor that restarts it on crash. V1's voice stack crashed the entire bot four times in one evening from native aborts; isolation is structural, not optional.
- Voice turns land in the same session file as text, marked `voice`. A voice session has identical summaries and context updates.
- Voice commands for sleep state: "going to bed", "can't sleep", "I'm awake".

---

## 11. Chat runtime

### 11.1 Router

Deterministic intents first (task/list/reminder CRUD, sleep state, calendar quick-add, recipe lookup, "run agent"), each scored 0–1. Top match > 0.7 and at least 0.15 above the runner-up → execute. Ambiguous between intents → ask a one-line clarifying question. No match → Claude. Every decision logged to `log/routing.md` (input, ranked matches, choice, confidence). Tolerate the V1-observed STT mishearings ("i'd"/"id" for "add").

### 11.2 Prompt assembly (in this order, token-budgeted)

1. System: `docs/instructions/<purpose>.md` + personality dials (§21).
2. `memory/profile.md` (human-owned).
3. `memory/personal-context.md`.
4. Project `context.md` (if in a project).
5. Retrieved chunks: `search(message, project=current)`, top 6, deduped against what's already in context.
6. Current session: last N turns verbatim; older turns replaced by a rolling summary stored in session state.
7. The message.

### 11.3 Tools Sunny has during chat

So the main assistant can query a whole project, or everything, on its own judgment:

- `search(query, project?, kinds?, tags?, since?, mode?)`
- `list_sessions(project, since?, tags?)`
- `read_session(id, turn_range?)` — full transcript on demand
- `read_context(project)`, `read_source(id, section?)`
- `list_projects()`
- Task, calendar, recipe, and agent tools from the registry (§12)
- `web_search` — only callable when the user explicitly asked to look something up (enforced in the gateway, not just the prompt)

### 11.4 Gateway rules (carried from V1, all mandatory)

- One gateway module; a semaphore caps concurrent Claude calls (default 1 awake, 2 during sleep).
- Daily and monthly spend caps checked before every call; sleep-mode jobs have their own sub-budget so overnight work can't eat the day's budget.
- An auth latch trips permanently on `AuthenticationError` until restart.
- Never log exception messages from connection errors (they can contain the key); log the type.
- Every call (success or refusal) appended to `log/llm-usage.md` and the usage table: purpose, model, tokens, cost, latency.
- Streaming for chat and voice; JSON-schema mode for all structured outputs.

---

## 12. Agent system

### 12.1 Loop

- Runs every 5 minutes while Awake or Can't Sleep, on manual trigger from the UI or chat, and in batch mode during Sleeping (§14).
- Each cycle: record cycle-start commit hash → pull queued tasks by priority/deadline → execute → log → commit.
- On unrecoverable error: `git revert` to the cycle-start commit, mark the task `failed`, notify at ALERT tier with error context.

### 12.2 Task queue

`tasks-queue/<id>.yaml`:
```yaml
id: tsk_01J...
created: ...
status: queued          # queued | running | done | failed
priority: 2             # 1 high .. 4 low
deadline: null
agent: default
source: user            # user | extraction | agent
description: ...
result: null
```

### 12.3 Tool synthesis

- The agent may request a tool: `{name, description, inputs (JSON schema), code}`.
- Names are intention-driven (`fetch_ksu_assignment_deadlines`, not `get_page_3`). Reject names that encode ids or dates.
- Write to `tools/<name>.py`, register in `tools/registry.yaml` (`name, version, created, creator, success, failure, status`), commit `synth: <name>`.
- Synthesized tools execute in a **subprocess worker with a timeout and memory limit**. This is crash isolation, not a permission gate: a bad tool must not take down the server.
- Three failures → `status: broken`, hidden from agents until re-enabled in the admin panel.
- Built-in tools: `fetch_calendar`, `create_calendar_event`, `sync_nextcloud_to_google`, `log_to_vault`, `notify`, `search`, `create_task`, `read_session`.

### 12.4 Proactivity tiers

| Tier | Behavior | Used for |
|---|---|---|
| SILENT (default) | Execute, log | Routine work |
| QUIET | Log + mention in next briefing | Findings, completed background work |
| SUGGEST | Propose, wait for approval | Anything destructive; every anticipatory action (calendar blocks, stale-task cleanup) |
| ALERT | Push notification | Unresolvable calendar conflicts, sync failure, tool broken ×3, git corruption, contradictory facts |

Anticipatory actions are always SUGGEST: they appear in the briefing with Approve / Dismiss and execute only on approval.

---

## 13. Extraction rules

- `docs/extraction-rules.md` holds the rules. Each rule is a markdown section with a fenced YAML block: `name, tier (1|2|3), pattern (regex), negations, examples, confidence, output`.
- Rules run on every closed session transcript and every chat turn from Keaton. Pure Python — no Claude calls.
- Gates: > 0.85 auto-write to `memory/facts/` and the relevant context file; 0.7–0.85 queue for briefing approval; < 0.7 log only.
- Every decision logged to `log/extraction.md` with the matched rule name.
- Tiers: 1 Keaton-specific (preferences, goals, history, constraints), 2 contextual (people, events, external references), 3 personality (jokes, abbreviations, running references, speech patterns).
- Ship 15–20 starter rules covering preferences, goals with deadlines, people, abbreviations, and running jokes, each with positive and negative test cases.
- Hot reload on file change; a malformed rule is skipped and reported, never crashes the engine.

---

## 14. Sleep state machine

States: **Awake | Sleeping | Can't Sleep**. Changed by UI toggle or voice/chat command; persisted; every transition logged.

- **Awake:** normal operation, 5-minute agent cycles.
- **Sleeping:** zero notifications, zero voice, ALERT tier queues instead of pushing. Batch jobs run in this order, each with its own time and spend budget, each writing to `reports/`:
  1. Retry pending session summaries.
  2. Context consolidation for every project touched today (§7.3).
  3. Health analysis — last 24h Garmin data → `reports/health/`.
  4. Deep research — up to 3 topics Keaton queued → pathfinder (§9.4).
  5. Tool review — DEEP-model review of tools created or failed recently: useful, fragile, improvements.
  6. Self-check — log error counts, tool failure rates, broken wikilinks, orphaned files, index vs. disk drift, git integrity, sync conflicts.
  7. Auto-ideation — the idea loop (§17) on improvements Sunny thinks it needs → `ideas-auto/`.
  8. Sleep report — compile all of the above into `reports/sleep/<date>.md`.
- **Can't Sleep:** Awake behavior, dark UI, and it pre-runs the cheap parts of the batch (1, 2, 6) so the eventual sleep report is ready sooner.
- **Waking:** the morning briefing (§18.2) is assembled from the sleep report and shown immediately. A 5 a.m. day boundary (V1 `day_boundary`) decides which day "today" is.

If Keaton forgets to toggle, nothing runs overnight; the briefing notes that the batch didn't run and offers to run it now.

---

## 15. Calendar

- **Nextcloud is the source of truth.** All reads and writes go through `caldav` against `NEXTCLOUD_CALDAV_URL`.
- **Google Calendar is a one-way mirror.** Hourly `sync_nextcloud_to_google`: match by UID stored in Google extended properties (fall back to title + start); create missing, update changed, delete events removed from Nextcloud. Never read Google back into Nextcloud.
- Real-time conflict detection when an event is created or changed; unresolvable overlaps → ALERT.
- Agent-suggested blocks are SUGGEST tier and visually distinct in the UI.
- Port V1's class-setup wizard (syllabus → recurring events + deadlines, preview → commit) onto Nextcloud.

---

## 16. Health

- Garmin via the unofficial `garminconnect` library, twice-daily pull, one-time backfill guarded by a persisted marker (as V1).
- Signals only: stress, sleep duration and quality, recovery / body battery, resting HR, VO2 max trend, training load. No macros.
- Port V1's readiness score with its visible, env-tunable weights.
- Weather and barometric pressure capture continues (migraine correlation) — it's the one series that can't be backfilled.
- Output is data plus short factual hints, never prescriptions. Hints appear in the afternoon briefing section or the health report — never as the first thing in the morning and never as a push.
  - Acceptable: "Sleep averaged 6.2 h over 5 nights, down from 7.1."
  - Not acceptable: "You should work out today!" or "Nice progression!"
- Weekly narrative in the Sunday health report: trend direction per signal, what changed, stated plainly.

---

## 17. Idea refinement

- Loop: Keaton explains → Sunny expands (scope, dependencies) → Sunny attacks (risks, edge cases, prior art, what's hard) → Sunny asks clarifying questions → Keaton answers → repeat until he stops it.
- Sunny's job is to sharpen *his* idea, not replace it with its own; questions come before suggestions.
- Stored at `ideas/<slug>.md`: `name, what, why, risks_identified, questions_answered, next_steps, refined_by_n_cycles`, with each cycle committed to git.
- Auto-ideation writes to `ideas-auto/` and appears in the morning briefing for Approve (moves to `ideas/`) or Dismiss (archived).

---

## 18. Reports and briefing

### 18.1 Reports dashboard

- Report types: action (hourly), research (per run), health (morning + weekly), ideas, sleep.
- Timeline of the last 7 days of agent actions, filterable by type and tier.
- Drill-down: action → full log entry, git commit hash, diff, revert button.
- Summary cards: tools created, research completed, sessions summarized, open suggestions.
- Every report exportable as markdown.

### 18.2 Morning briefing

Scannable, no narrative, no emoji:

```
SLEEP        7h12  quality 81  recovery 74%
RESEARCH     <topic> — 14 sources — [report]
TOOLS        <tool>: <status> — <one-line finding>
IDEAS        <idea> — <why> — [approve] [dismiss]
SUGGESTED    Thu 15:00–18:00  FSAE CAD block — [approve] [dismiss]
TODAY        09:30  ACCT 2100
             12:00–15:00  free
TASKS        [ ] <task> — due Fri
PENDING      2 extracted facts to confirm
ISSUES       none
```

Evening briefing switches in after 18:30 (V1 rule), but an explicit request always wins.

---

## 19. Recipes

`recipes/<slug>.yaml`: `id, name, tags, ingredients, steps, prep_time_min, cook_time_min, servings, source, rating, status, last_made, tried_count`. Search by ingredient, tag, and time; "log made" increments counters. Standalone — no health or meal-planning integration.

---

## 20. Frontend

### 20.1 Screens

- **Home** — briefing, calendar strip (7 days, suggested blocks marked), task queue, quick-add (+task, +reminder, run agent), sleep-state toggle.
- **Projects** — project list → project page with sessions list, context.md view (machine sections rendered, human section editable), research folders, files.
- **Session** — Claude-style chat: streaming replies, voice button (PTT / hands-free), inline citations, "move to project", rename, tags, "open full transcript".
- **Research** — sources panel (drag-drop import, status per source), chat, report tab.
- **Search** — global hybrid search with filters (project, kind, tags, date, mode).
- **Reports** — timeline, cards, drill-down, export.
- **Ideas**, **Recipes**.
- **Admin** — extraction rules editor, tool registry, git log with revert, sync status (Syncthing API, conflict files), integration health, spend panel, routing log.

### 20.2 Visual direction

Neo-brutalism with selective Y2K. Anti-minimal, anti-template.

- Base: crisp white and light silver. Hard black borders (2–3px), offset solid shadows, no blur shadows, no soft gradients except deliberate iridescent accents on active states.
- Accents, used semantically and only these:
  - `#f7d101` optic yellow — CTAs, highlights, focus
  - `#2596be` cyan — Sunny, system state, data
  - `#c80f67` magenta — priority, alerts, volatility
- Type: a strong grotesk for UI and a monospace for data, times, and logs. No default system-font look.
- Dense, scannable layouts. Mobile-first; every screen usable one-handed on a phone.
- Dark mode for Can't Sleep and night use: near-black base, same accents.
- No stock illustrations, no generated imagery, no emoji, no placeholder copy like "Welcome back!". Empty states state facts ("No sessions in this project.").
- Put all tokens in one `theme.ts`/CSS variables file so Keaton can adjust by hand.

### 20.3 PWA and notifications

Installable PWA. Web Push via VAPID (keypair generated once, never regenerated; expired subscriptions pruned on 404/410). Push is used only for ALERT tier and reminders.

---

## 21. Personality

- JARVIS / Muse: competent, calm, dry, precise. Anticipates, never fusses.
- No emoji. No exclamation marks. No "Great question", "Awesome", "Happy to help", "Let me know if…".
- Facts first, shortest accurate phrasing. Uncertainty stated plainly.
- Dry humor is allowed sparingly and should draw on the tier-3 running references when they fit.
- `docs/personality.md` is human-owned and provides dials (verbosity, dryness, formality). It's injected into the system prompt; if the file is malformed, fall back to the last good version.
- Default system prompts live in `docs/instructions/` (`chat.md`, `research.md`, `voice.md`, `briefing.md`, `ideas.md`, `summarize.md`), hot-reloaded.

---

## 22. Carry-over from V1

### Keep and port (behind the new router)

- `day_boundary` (5 a.m. day, 18:30 evening switch)
- Readiness score with tunable weights; weather/pressure capture; `location_resolves()` validation before saving a location
- Web Push service
- `warren_watch` (edge-triggered status bridge for the Warren trading bot; persisted last status)
- Spotify playback commands
- Class-setup wizard and exam-prep spaced review (retargeted to Nextcloud)
- Restart marker + crash detection on boot (call one helper; don't duplicate the logic inline)
- Settings TTL live reload and `looks_configured()`

### V1 incidents your code must not repeat

- **FD leak:** `with sqlite3.connect() as conn` commits but never closes. All SQLite access goes through `db.closing_transaction()` or a pooled long-lived read connection for hot paths. Add a test that runs 5,000 calls and asserts the open-FD count is stable.
- **Shared connection across threads/loops** broke the usage panel: per-thread connections plus a lock for writes.
- **Discord-style startup that never ran under bare uvicorn:** all loops start from the ASGI lifespan with a double-start guard.
- **Native crashes invisible to Python logging:** journal scan on boot when no restart marker exists.
- **Location string saved without validation** 404'd forever: validate integrations' config values live before persisting.

### Migration

`scripts/migrate_v1.py`: import V1 tasks, lists, projects, and memory facts from the V1 vault layout into V2's. Idempotent, never deletes originals, dry-run flag. Test against a synthetic V1-shaped fixture.

### Dropped — do not build

Discord bot, `vault_permissions` gate, `context_engine.py`, prescriptive workout suggestions, rules-engine notification consumer, Pi companion wake-word streaming path, recipe–health integration, any paid API other than Claude.

---

## 23. Security and secrets

This build runs on a rented machine. Therefore:

- Commit only `.env.example` with placeholders ending in `...`.
- Never request, generate, or embed real credentials. All integration tests use fakes.
- Use `fixtures/vault/` (synthetic) for every test and demo. Do not create realistic personal data.
- Token files (Google, Spotify, Garmin, Nextcloud) are created on the M-700 at deploy time, stored under `.sunny/secrets/` with `chmod 600`, and excluded from git and Syncthing.
- The app binds to `0.0.0.0` inside Docker but is meant to be reached only over Tailscale; add a single-user login (password hash from env + long-lived session cookie) anyway.
- Path-traversal guard on every file read/write that takes a user- or model-supplied path.

---

## 24. Build phases

Each phase ends with its checks passing and a commit.

**P0 — Skeleton.** Repo layout, config, db helpers, vault IO + git_ops, lifespan loop registry, logging, Docker Compose (sunny + syncthing + nextcloud), health endpoint, CI script running tests.
✓ `docker compose up` serves `/health`; FD-stability test passes; atomic write and marker-region tests pass.

**P1 — Vault, projects, sessions.** Project/session CRUD, frontmatter schemas, file ownership + marker regions, watcher, external-edit deferral, conflict detection, git commit per write batch.
✓ Create project → session → append turns → move session → all reflected on disk and in git; external edit to `context.md` is preserved.

**P2 — Index and search.** Chunker, FTS5, fastembed + sqlite-vec, hybrid RRF, filters, watcher-driven reindex, `reindex.py`.
✓ Fixture vault indexes; keyword, semantic, and hybrid queries return expected hits; reindex from scratch matches incremental state.

**P3 — Chat runtime and context system.** Router with confidence scoring and audit log, gateway with caps/latch/semaphore/streaming, prompt assembly, chat tools, session close hook, context and personal-context merge.
✓ With a fake Claude, a session closes and produces frontmatter summary, context.md updates, personal-context.md updates, extraction run, commit.

**P4 — Frontend core.** Design tokens, Home, Projects, Session (streaming), Search, Admin shell, login, PWA manifest.
✓ Full text chat inside a project works end to end against the fake gateway; Lighthouse PWA installable.

**P5 — Research.** Research sessions, all ingest extractors, dedupe, citations, report generation, explicit-lookup path in normal chat, pathfinder with all free sources behind fakes.
✓ Import one of each source kind from fixtures; cited answer resolves to the exact passage; web_search is refused unless the user asked.

**P6 — Agent.** Loop, task queue, tool registry, synthesis, subprocess sandbox, revert-on-failure, proactivity tiers, notify registry + Web Push.
✓ A synthesized tool that raises is reverted and marked broken after 3 failures; the server stays up.

**P7 — Extraction.** Rules parser, engine, gates, audit log, starter rules with tests, hot reload.
✓ Every starter rule's positive examples match and negatives don't.

**P8 — Sleep state, reports, briefing.** State machine, batch pipeline with budgets, all report types, dashboard timeline and drill-down, morning/evening briefing, suggestion approve/dismiss.
✓ Simulated night with fakes produces a sleep report and a morning briefing matching §18.2's shape.

**P9 — Calendar.** CalDAV client, conflict detection, Google mirror with UID matching, class-setup wizard port.
✓ Against a fake CalDAV server: create/update/delete mirror correctly; conflicts raise ALERT.

**P10 — Health.** Garmin ingest, readiness, pressure capture, hints, weekly narrative.
✓ Fixture Garmin data produces a health report with no prescriptive language (add a test that greps hints for "should", "!", and emoji).

**P11 — Voice.** Audio worklet, WS protocol, isolated child process with supervisor, VAD, Vosk partials, faster-whisper finals, Piper streaming, sleep-state voice commands.
✓ Recorded fixture WAV → final transcript appended to a session as a `voice` turn; killing the child process doesn't affect the web server and the supervisor restarts it.

**P12 — Ideas and recipes.** Refinement loop UI, iteration commits, auto-ideation queue, recipe CRUD and search.

**P13 — Carry-overs and migration.** Everything in §22 "keep and port", `migrate_v1.py`.

**P14 — Hardening and deploy.** Backup script (vault git bundle + SQLite `.backup`), restart script with marker, README with first-run steps on the M-700 (Syncthing pairing, Nextcloud setup, OAuth sign-ins, Garmin credentials), final full test run.

---

## 25. Definition of done

- Every phase checked off in `PROGRESS.md`; `BLOCKERS.md` lists only things that genuinely need Keaton's credentials or hardware.
- `pytest` passes offline; `docker compose up` on a clean machine brings up a working app against the fixture vault.
- README explains, in order: deploy to M-700, pair Syncthing with the PC, create the Nextcloud user and calendar, connect Google/Garmin/Spotify, set spend caps, and how to revert anything via git.
- Nothing in the UI, prompts, or reports uses emoji, exclamation marks, or filler phrasing.
