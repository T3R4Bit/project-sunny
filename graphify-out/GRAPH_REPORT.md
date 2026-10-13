# Graph Report - Project-SUNNY  (2026-10-10)

## Corpus Check
- 132 files · ~60,988 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2141 nodes · 3893 edges · 137 communities (126 shown, 11 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 380 edges (avg confidence: 0.87)
- Token cost: 231,838 input · 0 output

## Community Hubs (Navigation)
- CalDAV Calendar Sync
- Vault Frontmatter & Atomic IO
- Source Ingest Extractors
- Projects Service Core
- Sleep State Machine
- Data Migration
- Extraction Rules Parser
- React Frontend App
- Agent Batch Pipeline
- Research API Tests
- Frontend API Tests
- Intent Router
- Vault Marker Regions
- Close Hook Extraction Tests
- Chat Session Turns
- Wake Word Detection
- Agent Loop Execution
- Auth & Login
- Projects HTTP Routes
- Project & Session CRUD Tests
- Garmin Health Sync
- Rules Engine & Fact Writes
- Hybrid Search (RRF)
- Recipes Manager
- Agent Control API
- Chat Tool Registry
- Health Insights
- Voice Pipeline Tests
- Vault Git Ops
- Task Carryover
- Ideas Manager
- Frontend Dependencies
- App Startup & Lifespan
- Notification Tiers
- Frontend TS Config
- YAML Task Queue
- Index File Watcher
- Vault Path Layout
- Research Service
- Text Chunker
- Build Progress Log
- Tool Registry & Synthesis
- FTS5 Keyword Index
- Prompt Assembly
- Research Models
- Sync Conflict Watcher
- Lab Run Spec & Phases
- Index Service Tests
- Starter Extraction Rules
- Settings & Config
- FD Leak Regression Tests
- Extraction Logging & Hot Reload
- Memory Write Gate Thresholds
- Research Listing & Citations
- Voice Interaction
- Live Registry & Log Hygiene
- Agent Rules & Blockers
- V2 Core Concepts
- Briefing Loader Tests
- Briefing Data Loading
- LLM Gateway Auth Latch
- Report Rendering
- Login Rate Limiting
- SQLite DB Helpers
- Health Endpoint
- Reindex Tests
- Projects API Tests
- Rules Hot Reload
- LLM Chat Completion
- Login Tests
- Compose Stack & Calendar
- Gateway & Security Policy
- Task Queue Tests
- Report Tables
- Report Generator
- Project Disk Helpers
- Agent Proactivity Concepts
- PWA Manifest
- Vite Node TS Config
- Subprocess Tool Worker
- Close Hook Section Merge
- Spend Cap Checks
- Tool Naming Rules
- Proactivity Tier Tests
- Lab Inference Infra
- Non-negotiables & Personality
- Vault Ownership Model
- Setup Script
- Agent Test Fixtures
- Agent State Tests
- External Edit Preservation
- Agent Briefing Context
- LLM Usage Cost Log
- System Prompt Loading
- Recorded Decisions
- Shared Pytest Fixtures
- Index Chunk Removal
- Tool Handler Registry
- Subprocess Worker Tests
- Extraction Test Fixtures
- Index Search Route
- Spend Tracking Reset
- Text-to-Speech
- Speech-to-Text
- Checkpoint & Teardown Scripts
- Tool Registry Tests
- test_agent fragment 106
- models fragment 107
- icon-192 fragment 108
- batch fragment 109
- fetch_models fragment 110
- ci fragment 111
- pyproject fragment 134

## God Nodes (most connected - your core abstractions)
1. `read_file()` - 38 edges
2. `SleepStateMachine` - 35 edges
3. `RulesEngine` - 34 edges
4. `VoicePipeline` - 33 edges
5. `RulesParser` - 32 edges
6. `get_settings()` - 31 edges
7. `DataMigration` - 30 edges
8. `BatchPipeline` - 29 edges
9. `atomic_write()` - 29 edges
10. `AgentLoop` - 28 edges

## Surprising Connections (you probably didn't know these)
- `Commands in sunny-sandbox, git on host` --semantically_similar_to--> `Run commands inside sunny-sandbox, never git`  [INFERRED] [semantically similar]
  DECISIONS.md → AGENTS.md
- `extraction_rules_fixture.md (test copy of rules)` --semantically_similar_to--> `extraction-rules.md (starter rule set)`  [INFERRED] [semantically similar]
  tests/test_extras/extraction_rules_fixture.md → docs/extraction-rules.md
- `Fixture rule: sleep_duration_mention (strict prefix)` --semantically_similar_to--> `Rule: sleep_duration_mention`  [INFERRED] [semantically similar]
  tests/test_extras/extraction_rules_fixture.md → docs/extraction-rules.md
- `TestBriefingLoader` --uses--> `BriefingContext`  [INFERRED]
  tests/test_p8_agent.py → backend/sunny/agent/briefing.py
- `main()` --calls--> `get_settings()`  [INFERRED]
  scripts/reindex.py → backend/sunny/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Sunny Docker Compose stack** — docker_compose_sunny, docker_compose_syncthing, docker_compose_nextcloud, docker_compose_nextcloud_db, docker_compose_sunny_network [EXTRACTED 1.00]
- **Agent working-state files** — progress, decisions, blockers, agents [EXTRACTED 1.00]
- **Agent task/tool execution flow** — progress_agent_loop, progress_task_queue, progress_tool_registry, progress_subprocess_worker, vault_tools_registry [INFERRED 0.85]
- **Prompt-injection defense chain for ingested content** — docs_spec_sunny_v2_security_shared_fetch_module, docs_spec_sunny_v2_security_extractor_worker, docs_spec_sunny_v2_security_github_ingest, docs_spec_sunny_v2_security_provenance_tag, docs_spec_sunny_v2_security_memory_write_gate [INFERRED 0.85]
- **Non-cuttable agent containment (items 11, 12, 14, 15)** — docs_spec_sunny_v2_security_real_sandbox, docs_spec_sunny_v2_security_credential_broker, docs_spec_sunny_v2_security_side_effect_approval, docs_spec_sunny_v2_security_memory_write_gate [EXTRACTED 1.00]
- **Session close pipeline (summary -> context merge -> extraction -> reindex)** — docs_spec_sunny_v2_build_prompt_session_close_hook, docs_spec_sunny_v2_build_prompt_context_system, docs_spec_sunny_v2_build_prompt_extraction_engine, docs_spec_sunny_v2_build_prompt_hybrid_search, docs_extraction_rules [EXTRACTED 1.00]

## Communities (137 total, 11 thin omitted)

### Community 0 - "CalDAV Calendar Sync"
Cohesion: 0.05
Nodes (32): CalDAVSync, CalendarEvent, datetime, Path, P9 — CalDAV calendar sync for Sunny. Reads/writes events via CalDAV (supports…, Parse an iCalendar string into a CalendarEvent., Add an event to the CalDAV calendar. Returns event UID or None., Find calendar conflicts for a given time range. (+24 more)

### Community 1 - "Vault Frontmatter & Atomic IO"
Cohesion: 0.06
Nodes (44): dump(), dump_file(), load(), load_file(), Any, Path, Frontmatter helpers — string-based frontmatter read/write. The ``frontmatter``…, Load frontmatter from a text string. (+36 more)

### Community 2 - "Source Ingest Extractors"
Cohesion: 0.05
Nodes (31): ABC, ArXivExtractor, AudioVideoExtractor, BaseExtractor, DocxExtractor, EPUBExtractor, ExtractorResult, GitHubExtractor (+23 more)

### Community 3 - "Projects Service Core"
Cohesion: 0.08
Nodes (50): context_file(), project_dir(), project_file(), Return the directory for a project slug., sessions_dir(), Project, ProjectUpdate, BaseModel (+42 more)

### Community 4 - "Sleep State Machine"
Cohesion: 0.07
Nodes (16): Enum, str, P8 — Sleep State Machine for the agent loop. Transitions between awake, can't…, Run one sleep/awake cycle. Args: task_exists: Whether there are pending tasks…, Record a heartbeat. Returns False if heartbeat timed out., Decide whether to sleep or stay awake based on task state., Return sleep/awake statistics., Reset state machine to initial state. (+8 more)

### Community 5 - "Data Migration"
Cohesion: 0.07
Nodes (20): DataMigration, MigrationResult, MigrationStep, Path, P13 — Data migration and version compatibility. Handles migrating data between…, Run all pending migrations., Detect current vault version., A single migration step. (+12 more)

### Community 6 - "Extraction Rules Parser"
Cohesion: 0.06
Nodes (25): Parse extraction rules from docs/extraction-rules.md., Parse rules from the markdown file content. Returns list of valid rules, logs…, Split content into YAML blocks separated by ---., Parse a single YAML block into a Rule., RulesParser, Rule with single negation string is handled., Rules have correct tier assignments., Rules can have examples. (+17 more)

### Community 7 - "React Frontend App"
Cohesion: 0.09
Nodes (24): App(), handleLogout(), navigate(), Page, Header(), useAuth(), login(), logout() (+16 more)

### Community 8 - "Agent Batch Pipeline"
Cohesion: 0.10
Nodes (18): asyncio, BatchPipeline, BatchResult, BatchTask, Any, P8 — Batch Pipeline for grouping related tasks. Groups small tasks into batches…, Register a function that executes a batch., Pull and execute the next batch. Args: processor: Optional executor function.… (+10 more)

### Community 9 - "Research API Tests"
Cohesion: 0.07
Nodes (16): _citations_replace(), Replace bracketed citations like [S1] or [S1 §section] with HTML links., client(), fixture, Path, P5 Research — tests for research sessions, source ingest, dedup, citations,…, Source ingestion and dedup., Test client with vault path pointing to tmp_path. (+8 more)

### Community 10 - "Frontend API Tests"
Cohesion: 0.05
Nodes (41): Integration tests for P4 — frontend API endpoints. These tests verify that the…, GET /projects/{slug} returns project details., DELETE /projects/{slug} removes project., POST /chats/sessions creates a Home session., POST /chats/sessions/{slug}/append adds a turn., POST /chats/sessions/{slug}/close closes a session., POST /projects/{slug}/sessions creates a session in a project., POST /projects/{slug}/sessions/{slug}/append adds a turn. (+33 more)

### Community 11 - "Intent Router"
Cohesion: 0.07
Nodes (29): _calc_confidence(), _extract_params(), _get_intent_patterns(), Intent, _log_routing(), Match, Enum, str (+21 more)

### Community 12 - "Vault Marker Regions"
Cohesion: 0.08
Nodes (18): ensure_markers(), get_machine_region(), merge_shared_file(), Merge new machine content into a shared file. Args: existing: current file…, Return content with a marked block for *section* if none exists. If a matching…, Return the text between sunny:begin/end markers for *section*. Returns empty…, Replace the machine region for *section* with *new_text*. If markers don't…, set_machine_region() (+10 more)

### Community 13 - "Close Hook Extraction Tests"
Cohesion: 0.15
Nodes (21): Run the close hook for a session. Args: session_slug: The session's…, run_close_hook(), patch, _get_rules_content(), Path, Test extraction runs end-to-end from close_hook., Helper to mock settings for a vault., run_close_hook triggers extraction rules engine. (+13 more)

### Community 14 - "Chat Session Turns"
Cohesion: 0.09
Nodes (33): append_home_turn(), append_project_turn(), chat_completion_endpoint(), chat_stream_endpoint(), close_home_session(), close_project_session(), create_session(), list_home_sessions() (+25 more)

### Community 15 - "Wake Word Detection"
Cohesion: 0.09
Nodes (11): P11 — Lightweight wake word detection. Simple keyword matching for wake word…, Result of wake word detection., Detects wake words in audio transcript text., Get or create a pre-compiled regex pattern for the given word., Get or create the pre-processed substring for the given word., Check if any wake word is present in the text., WakeWordDetector, WakeWordResult (+3 more)

### Community 16 - "Agent Loop Execution"
Cohesion: 0.09
Nodes (18): AgentLoop, Any, Path, Execute tasks as a batch., Generate a daily/periodic report., Execute a single task based on its type., Handle default agent tasks., Handle synthesis tasks (tool creation, deep analysis). (+10 more)

### Community 17 - "Auth & Login"
Cohesion: 0.10
Nodes (31): auth_status(), _check_rate_limit(), _clean_expired_sessions(), _create_session(), _get_admin_hash(), _get_client_ip(), _get_session(), login() (+23 more)

### Community 18 - "Projects HTTP Routes"
Cohesion: 0.10
Nodes (31): home_chats_dir(), home_session_file(), archive_project(), clear_sync_conflicts_endpoint(), close_home_session(), close_session(), create_home_session(), create_project() (+23 more)

### Community 19 - "Project & Session CRUD Tests"
Cohesion: 0.12
Nodes (11): ProjectCreate, SessionClose, file_hash(), Path, Read a vault file, returning None if it doesn't exist., Return SHA-256 hex digest of a file, or None., read_file(), Full pipeline: create project → session → append turns → move → on disk. (+3 more)

### Community 20 - "Garmin Health Sync"
Cohesion: 0.10
Nodes (17): GarminSync, HealthInsight, HealthMetric, datetime, Path, P10 — Garmin health data sync for Sunny. Reads sleep, heart rate, steps, and…, Fetch data from Garmin Connect API., Load cached health data. (+9 more)

### Community 21 - "Rules Engine & Fact Writes"
Cohesion: 0.11
Nodes (19): Apply extraction rules to text content., Replace all rules and pre-compile patterns., A single extraction rule., Rule, RulesEngine, Test rule matching, negation, and classification., Rules match when pattern found., Multiple matches from same rule. (+11 more)

### Community 22 - "Hybrid Search (RRF)"
Cohesion: 0.12
Nodes (27): Hit, A single search result., _hits_to_results(), date, Index service — orchestrates chunking, indexing, and hybrid search. Ties…, Unified search with three modes. Args: query: Search text. project: Filter by…, Convert FTS Hit objects to SearchResult objects., Convert VectorHit objects to SearchResult objects. (+19 more)

### Community 23 - "Recipes Manager"
Cohesion: 0.12
Nodes (13): Path, P12 — Recipe management and meal planning for Sunny. Store recipes with…, Find recipes matching criteria., Generate a meal plan for the next N days., Generate a shopping list from a meal plan., Load a recipe from its markdown file., A single ingredient in a recipe., Manage recipes and generate meal plans. (+5 more)

### Community 24 - "Agent Control API"
Cohesion: 0.13
Nodes (27): AgentState, get_agent_loop(), Enum, str, Agent loop — background task scheduler for Sunny. Integrates P8 sleep state…, Get the global agent loop, creating if needed., Start the agent loop (called from lifespan)., Stop the agent loop (called from lifespan). (+19 more)

### Community 25 - "Chat Tool Registry"
Cohesion: 0.09
Nodes (12): ChatTool, ChatToolRegistry, Any, Call a tool by name with arguments., Web search — should only be called when user explicitly asked., A single chat tool definition., Registry of tools available during chat., Register all built-in chat tools. (+4 more)

### Community 26 - "Health Insights"
Cohesion: 0.10
Nodes (12): HealthInsight, HealthInsights, Path, P10 — Health insights engine. Analyzes health data from Garmin to detect…, Analyze heart rate data and return insights., Generate a health summary from all insights., A derived health insight., Analyzes health metrics and generates insights. (+4 more)

### Community 27 - "Voice Pipeline Tests"
Cohesion: 0.15
Nodes (9): Manages the voice interaction pipeline., Check if voice pipeline has required components., Check if text contains the wake word., VoicePipeline, Path, P9-P13 — Calendar, Health, Voice, Ideas, Recipes, Migration tests., Test optimized voice pipeline features., TestVoicePipeline (+1 more)

### Community 28 - "Vault Git Ops"
Cohesion: 0.11
Nodes (16): get_head_commit(), Return the current HEAD commit hash or None., Return vault git status dict: {ahead, behind, has_changes}., Revert the vault to a specific commit hash. Returns True on success., revert_to(), status(), git_repo(), fixture (+8 more)

### Community 29 - "Task Carryover"
Cohesion: 0.13
Nodes (12): Carryover, CarryoverManager, datetime, Path, P13 — Task carry-over tracking. Handles automatic carry-over of incomplete…, Mark a carry-over as resolved., Generate a summary of carry-over stats., Manages task carry-overs. (+4 more)

### Community 30 - "Ideas Manager"
Cohesion: 0.13
Nodes (12): Idea, IdeasManager, Path, P12 — Ideas management for Sunny. Capture, tag, retrieve, and review ideas.…, Review and score an idea., Get most-scored ideas from recent days., Load an idea from its markdown file., Render idea as markdown. (+4 more)

### Community 31 - "Frontend Dependencies"
Cohesion: 0.07
Nodes (26): dependencies, react, react-dom, workbox-window, devDependencies, @types/react, @types/react-dom, typescript (+18 more)

### Community 32 - "App Startup & Lifespan"
Cohesion: 0.11
Nodes (24): AbstractEventLoop, Index service — search API routes., Stop the background index watcher task., stop_index_watcher(), create_app(), get_all_loops(), get_loop(), lifespan() (+16 more)

### Community 33 - "Notification Tiers"
Cohesion: 0.10
Nodes (17): get_notify_registry(), notify(), NotifyRegistry, NotifyTier, Enum, str, Notify registry — proactivity tiers for agent actions., Registry of notification handlers by tier. (+9 more)

### Community 34 - "Frontend TS Config"
Cohesion: 0.08
Nodes (24): compilerOptions, allowImportingTsExtensions, baseUrl, isolatedModules, jsx, lib, module, moduleResolution (+16 more)

### Community 35 - "YAML Task Queue"
Cohesion: 0.15
Nodes (13): _now_iso(), Any, Path, Task queue — YAML-based task management for the agent loop., YAML-based task queue stored in tasks-queue/., Add a task to the queue. Returns task ID., Get the next N queued tasks sorted by priority then deadline., Mark a task as running. (+5 more)

### Community 36 - "Index File Watcher"
Cohesion: 0.14
Nodes (21): index_chunk(), Index a single chunk in the database., _classify_path(), index_all_from_vault(), _initial_index(), _needs_reindex(), _poll_changes(), Path (+13 more)

### Community 37 - "Vault Path Layout"
Cohesion: 0.19
Nodes (22): docs_dir(), extraction_log(), facts_dir(), facts_file(), ideas_auto_dir(), ideas_dir(), instructions_dir(), instructions_file() (+14 more)

### Community 38 - "Research Service"
Cohesion: 0.17
Nodes (20): get_extractor(), SourceIngest, create_research(), ingest_source(), post, Research router — API for research sessions and source ingest., Create a new research session., Ingest a source into a research session. (+12 more)

### Community 39 - "Text Chunker"
Cohesion: 0.13
Nodes (13): chunk_session_file(), chunk_source_file(), chunk_text(), _chunk_window(), Vault chunker — split text into overlapping segments for indexing., Parse a session file and produce chunks, one per turn group., Chunk an extracted source file., Split text on markdown headings into sections. (+5 more)

### Community 40 - "Build Progress Log"
Cohesion: 0.12
Nodes (20): context.md uses sunny:begin/end marker regions, String-based frontmatter helpers, src/main.tsx entry, PWA manifest.json, AgentLoop (AWAKE/CANT_SLEEP/SLEEPING/OFF), Build phases P0-P14, Session close hook, React + Vite + TypeScript frontend (+12 more)

### Community 41 - "Tool Registry & Synthesis"
Cohesion: 0.14
Nodes (10): Path, Register a tool (used for synthesized tools)., Get all active tools., Mark a tool failure. 3 failures → broken., Synthesize a new tool. Writes to tools/<name>.py and registry.yaml., Registry for agent tools (built-in + synthesized)., Register built-in tools., Load synthesized tools from tools/ directory. (+2 more)

### Community 42 - "FTS5 Keyword Index"
Cohesion: 0.18
Nodes (12): Chunk, A single indexed chunk of text., add_chunk(), init_fts(), Connection, Path, FTS5 keyword search — lightweight full-text indexing over vault files. SQLite…, Run an FTS5 keyword search using bm25() scoring. Returns Hit instances sorted… (+4 more)

### Community 43 - "Prompt Assembly"
Cohesion: 0.15
Nodes (15): assemble_prompt(), _format_chunks(), _format_session_history(), _format_turns(), _load_file(), _load_project_context(), Prompt assembly — builds the full prompt for LLM calls. Assembly order (token-…, Load a file from the vault, returning None if missing. (+7 more)

### Community 44 - "Research Models"
Cohesion: 0.18
Nodes (12): research_source_dir(), now_iso(), BaseModel, Path, Research session models and service., Write source to disk: original, extracted.md, meta.yaml., ResearchCreate, ResearchSession (+4 more)

### Community 45 - "Sync Conflict Watcher"
Cohesion: 0.16
Nodes (14): external_edit_since(), _mark_external_edit(), Path, Vault file watcher — detects external edits and sync conflicts. Uses watchfiles…, Record that an external process edited this path., Return True if the path was externally edited within the last *seconds*., Record a sync conflict file., Scan the vault for existing sync conflict files. (+6 more)

### Community 46 - "Lab Run Spec & Phases"
Cohesion: 0.13
Nodes (18): LAB_RUN.md (lab environment rules), KSU AI Lab NVIDIA DGX (GB10, ARM64), Pacing rules (P0-P4 must, P5-P8 target, P9-P14 stretch), push_checkpoint.sh, Resume prompt, sunny-qwen-engine (local inference, port 8000), sunny-sandbox container, SUNNY_V2_BUILD_PROMPT.md (full specification) (+10 more)

### Community 47 - "Index Service Tests"
Cohesion: 0.20
Nodes (7): index_text(), init_index(), Path, Initialize all index tables in the database., Index a text blob, returning the list of chunk rowids., When vector backend is disabled, search_vector returns empty., TestIndexService

### Community 48 - "Starter Extraction Rules"
Cohesion: 0.12
Nodes (17): extraction-rules.md (starter rule set), Rule: abbreviation_definition, Rule: deadline_mention, Rule: food_preference, Rule: goal_statement, Rule: keaton_name, Rule: location_mention, Rule: meeting_scheduled (+9 more)

### Community 49 - "Settings & Config"
Cohesion: 0.16
Nodes (11): get_settings(), field_validator, Return cached Settings; reload from env if TTL expired or .env mtime changed., Reload if .env file changed or TTL expired., All Sunny configuration, loaded from .env with 5-second TTL live reload., Return True when essential config values are present., During P0 scaffolding the vault may not exist yet., Attr-style access with cache. (+3 more)

### Community 50 - "FD Leak Regression Tests"
Cohesion: 0.17
Nodes (12): closing_transaction(), Open a connection, auto-rollback on any exception. V1 bug: connections were…, db_file(), _open_fd_count(), fixture, Path, FD-stability test — ensures closing_transaction doesn't leak file descriptors., Create a temporary SQLite database. (+4 more)

### Community 51 - "Extraction Logging & Hot Reload"
Cohesion: 0.14
Nodes (11): Hot reload for extraction rules — watch docs/extraction-rules.md for changes., ExtractionLog, Path, Extraction rules engine - parses rules, matches transcripts, gates findings.…, Log all extraction decisions to log/extraction.md., Log an extraction decision., Write an auto-written fact to memory/facts/., write_fact() (+3 more)

### Community 52 - "Memory Write Gate Thresholds"
Cohesion: 0.16
Nodes (10): ExtractionMatch, Run all rules against text, return matches., Classify matches into gate categories., A match found by the rules engine., Test that matches are correctly routed by confidence gate., Confidence >= 0.85 -> auto_write., Confidence 0.7-0.85 -> approve_queue., Confidence < 0.7 -> log_only. (+2 more)

### Community 53 - "Research Listing & Citations"
Cohesion: 0.13
Nodes (16): research_sources_dir(), get_research(), list_research(), list_sources(), get, List all research sessions., Get a research session., List sources in a research session. (+8 more)

### Community 54 - "Voice Interaction"
Cohesion: 0.13
Nodes (8): P11 — Voice pipeline: STT → LLM → TTS for Sunny. Handles speech-to-text input,…, Process a voice transcript through the pipeline., Trim interaction history to max_history., Call the LLM with the transcript., Fallback response when LLM is unavailable., A single voice interaction., Save voice interaction to vault., VoiceInteraction

### Community 55 - "Live Registry & Log Hygiene"
Cohesion: 0.13
Nodes (15): Hybrid search with reciprocal rank fusion, Deterministic intent router, Proactivity tiers (SILENT/QUIET/SUGGEST/ALERT), vault/log/routing.md (intent audit log), Test runs write into the live vault log, create_calendar_event tool, fetch_test_data tool (agent-synthesized), get_page_3 tool (agent-synthesized) (+7 more)

### Community 56 - "Agent Rules & Blockers"
Cohesion: 0.16
Nodes (14): AGENTS.md (agent rules), docs/spec/LAB_RUN.md, Run commands inside sunny-sandbox, never git, Sunny V2, P0 Docker Compose acceptance checks, Tailscale-only exposure (M-700), watchfiles dependency missing from requirements.txt, Commands in sunny-sandbox, git on host (+6 more)

### Community 57 - "V2 Core Concepts"
Cohesion: 0.19
Nodes (15): Context system (context.md + personal-context.md), Extraction rules engine (§13), Extraction tiers (1 Keaton-specific, 2 contextual, 3 personality), Hybrid search (FTS5 BM25 + sqlite-vec, RRF), Idea refinement loop, Markdown is the source of truth, Morning briefing (§18.2), Pathfinder (deep research pipeline) (+7 more)

### Community 58 - "Briefing Loader Tests"
Cohesion: 0.29
Nodes (6): BriefingLoader, Path, Loads agent briefing from vault data., Path, Test briefing context loading., TestBriefingLoader

### Community 59 - "Briefing Data Loading"
Cohesion: 0.14
Nodes (7): Load pending task descriptions., Load pending decision descriptions., Extract recent deadlines from extraction log., Generate a summary of the knowledge base., Load briefing and return as structured dict for LLM consumption., Load the full briefing context., Load all personal facts from memory/facts/.

### Community 60 - "LLM Gateway Auth Latch"
Cohesion: 0.20
Nodes (12): AuthStatus, GatewayState, get_auth_status(), init_gateway(), Enum, str, Sunny LLM gateway — Claude API gateway with caps, semaphore, streaming.…, Permanently trip the auth latch until restart. (+4 more)

### Community 61 - "Report Rendering"
Cohesion: 0.17
Nodes (7): Path, Generate a daily summary report., Generate a weekly summary report., Render the report as markdown., Save the report to the vault., Generate a report for a single session., Report

### Community 62 - "Login Rate Limiting"
Cohesion: 0.17
Nodes (8): client(), fixture, Tests for auth endpoint — login, logout, rate limiting., Reset rate limiter state before each test., After 5 failed attempts from same IP, login should be rate-limited., TestAuthStatus, TestLogout, TestRateLimit

### Community 63 - "SQLite DB Helpers"
Cohesion: 0.24
Nodes (11): _ensure_db(), get_read_connection(), init_db(), _init_tables(), Connection, Path, DB helpers — closing_transaction() and pooled read connections., Return a long-lived pooled read connection (one per thread). Used for hot read… (+3 more)

### Community 64 - "Health Endpoint"
Cohesion: 0.20
Nodes (9): TestClient, client(), fixture, Path, Test client with vault path pointing to tmp_path., app(), fixture, Health endpoint test — verifies the /health route. (+1 more)

### Community 65 - "Reindex Tests"
Cohesion: 0.23
Nodes (6): fixture, Path, Create a synthetic vault with markdown files., Reindex should find and index all markdown files., Running reindex twice produces the same number of chunks., TestReindex

### Community 67 - "Rules Hot Reload"
Cohesion: 0.22
Nodes (6): Path, Watch and reload extraction rules file on change., Start watching for file changes in background thread., Load and apply rules from the file., Background loop that checks for file changes., RulesHotReload

### Community 68 - "LLM Chat Completion"
Cohesion: 0.20
Nodes (11): _generate_summary(), Call the LLM to generate session summary data., chat_completion(), _do_call(), Any, Send a chat completion request. Args: messages: List of {role, content} dicts.…, Execute the actual API call., Update spend tracking based on token usage. (+3 more)

### Community 69 - "Login Tests"
Cohesion: 0.18
Nodes (6): When admin_password_hash is empty (P0), login accepts any non-empty password., Login with correct password hash succeeds., Login with wrong password returns 401., Login success sets a session cookie with HttpOnly and SameSite=Strict., Login with no password or password_hash returns 400., TestLogin

### Community 70 - "Compose Stack & Calendar"
Cohesion: 0.29
Nodes (10): Docker Compose security baseline, docker-compose.yml (Sunny stack), nextcloud calendar service, nextcloud-db (mariadb), sunny backend service, sunny bridge network, syncthing service, CalDAV calendar sync (P9) (+2 more)

### Community 71 - "Gateway & Security Policy"
Cohesion: 0.22
Nodes (10): Fake Claude gateway (no API key), llm/gateway.py (single Claude gateway), Model tiers FAST/DEFAULT/DEEP, Research sessions (NotebookLM-style), Source ingest extractors, web_search gating (only on explicit request), Extractor worker (no secrets, no vault write), Safe GitHub ingest (hooksPath=/dev/null, no submodules) (+2 more)

### Community 72 - "Task Queue Tests"
Cohesion: 0.24
Nodes (4): Path, Task queue CRUD operations., Tasks should be returned by priority (1 = high first)., TestTaskQueue

### Community 73 - "Report Tables"
Cohesion: 0.22
Nodes (5): P8 — Periodic report generation for Sunny. Generates summary reports from…, Render sections as a markdown table for embedding in reports., A single section of a report., render_report_table(), ReportSection

### Community 74 - "Report Generator"
Cohesion: 0.36
Nodes (4): Generates periodic reports from vault data., ReportGenerator, Test report generation., TestReportGenerator

### Community 75 - "Project Disk Helpers"
Cohesion: 0.25
Nodes (7): get_project_on_disk(), Path, Project, Tests for P1 — Vault, projects, sessions. Acceptance check: ✓ Create project →…, Helper to reload a project from disk., Provide a temporary vault directory., vault()

### Community 76 - "Agent Proactivity Concepts"
Cohesion: 0.25
Nodes (9): Rule: course_code, Agent loop (5-minute cycles, revert on failure), Calendar (Nextcloud primary, Google one-way mirror), Proactivity tiers (SILENT/QUIET/SUGGEST/ALERT), Tool synthesis (§12.3), Canary credentials, Credential broker, Real sandbox for synthesized tools (container/bubblewrap/gVisor) (+1 more)

### Community 77 - "PWA Manifest"
Cohesion: 0.22
Nodes (8): background_color, description, display, icons, name, short_name, start_url, theme_color

### Community 78 - "Vite Node TS Config"
Cohesion: 0.22
Nodes (8): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, include, vite.config.ts

### Community 79 - "Subprocess Tool Worker"
Cohesion: 0.25
Nodes (6): Execute a single batch task., check_memory_limit(), execute_tool_in_subprocess(), Subprocess worker — isolated tool execution with timeout and memory limits., Execute tool code in a subprocess with timeout and memory limits. Args: code:…, Check if we can enforce the memory limit (Linux only).

### Community 80 - "Close Hook Section Merge"
Cohesion: 0.29
Nodes (4): _merge_section(), Merge items into a marked section, respecting caps. If the section doesn't…, Tests for session close hook., TestCloseHook

### Community 81 - "Spend Cap Checks"
Cohesion: 0.36
Nodes (4): check_spend_caps(), Check if spend caps allow this call. Returns SpendStatus. Sleep-mode jobs use a…, Tests for LLM gateway with spend caps and auth latch., TestGateway

### Community 82 - "Tool Naming Rules"
Cohesion: 0.25
Nodes (4): Synthesizing new tools., Tool names must be intention-driven, not ID-based., Tool names must not encode dates., TestToolSynthesis

### Community 83 - "Proactivity Tier Tests"
Cohesion: 0.25
Nodes (5): Agent proactivity tiers: SILENT, QUIET, SUGGEST, ALERT., Verify all notification tiers are defined., Test that notify produces a log entry., Verify ALERT tier is used for broken tools., TestProactivityTiers

### Community 84 - "Lab Inference Infra"
Cohesion: 0.33
Nodes (7): Lab infra lives in lab/, lab/compose.yml (lab infra), inference-engine (vLLM Qwen3.6-35B-A3B-FP8), sunny-sandbox container, Cline coding agent, KSU AI Lab DGX build workflow, setup.sh

### Community 85 - "Non-negotiables & Personality"
Cohesion: 0.29
Nodes (7): Rule: running_reference, Non-negotiables (§2), Personality: JARVIS/Muse, router.handle(message, ctx), V1 incidents not to repeat (FD leak, shared conn, startup, native crashes), Voice pipeline (Vosk partials, faster-whisper finals, Piper, isolated child process), ZFS snapshots + off-box replica

### Community 86 - "Vault Ownership Model"
Cohesion: 0.29
Nodes (7): vault/io.py::atomic_write, File ownership and sunny:begin/end marker regions, M-700 homelab server (TrueNAS SCALE), Sunny V2 (self-hosted personal assistant), Synced vault (Syncthing, git on server only), Kill switch outside agent's reach, No public exposure (Tailscale only, ACLs)

### Community 87 - "Setup Script"
Cohesion: 0.52
Nodes (6): c_fail(), c_ok(), c_warn(), dc(), setup.sh script, step()

### Community 88 - "Agent Test Fixtures"
Cohesion: 0.33
Nodes (6): client(), fixture, P6 Agent — tests for agent loop, task queue, tool registry, synthesis,…, Reset the agent loop singleton and its tool registry before each test., Test client with vault path pointing to tmp_path., reset_agent_loop()

### Community 90 - "External Edit Preservation"
Cohesion: 0.29
Nodes (4): client(), fixture, Test client with vault path pointing to tmp_path., TestExternalEditPreservation

### Community 91 - "Agent Briefing Context"
Cohesion: 0.33
Nodes (4): BriefingContext, P8 — Agent briefing: morning context restoration. Loads the agent's knowledge…, The complete briefing for an agent session., Render the briefing as a markdown prompt string.

### Community 92 - "LLM Usage Cost Log"
Cohesion: 0.33
Nodes (6): _estimate_cost(), Log usage to log/llm-usage.md., Estimate cost from result tokens., A logged LLM usage entry., _record_usage(), UsageEntry

### Community 93 - "System Prompt Loading"
Cohesion: 0.33
Nodes (4): _default_system_prompt(), _load_system_prompt(), Load the system prompt for the given purpose., Default system prompt when no file is found.

### Community 94 - "Recorded Decisions"
Cohesion: 0.40
Nodes (5): Append-only session body while live, Login accepts any password when ADMIN_PASSWORD_HASH is empty, git_ops.status() handles missing upstream, In-memory session store for auth (P0), backend/sunny/auth.py (login hardening)

### Community 95 - "Shared Pytest Fixtures"
Cohesion: 0.33
Nodes (5): fixture, Path, Shared pytest fixtures for Sunny tests., Provide a temporary vault directory with fixtures copied in., vault()

### Community 96 - "Index Chunk Removal"
Cohesion: 0.40
Nodes (5): Remove a chunk from the FTS index., remove_chunk(), Connection, Remove indexed chunks from the index., remove_indexed()

### Community 97 - "Tool Handler Registry"
Cohesion: 0.40
Nodes (5): get_tool_handler(), Any, Register a handler function for a tool., Get a tool handler by name., register_tool_handler()

### Community 98 - "Subprocess Worker Tests"
Cohesion: 0.40
Nodes (3): Tool execution isolation via subprocess., Test that tool execution returns a result., TestSubprocessWorker

### Community 99 - "Extraction Test Fixtures"
Cohesion: 0.40
Nodes (4): client(), fixture, P7 Extraction Rules Engine - tests for parser, matcher, gates, hot reload,…, Test client with vault path pointing to tmp_path.

### Community 100 - "Index Search Route"
Cohesion: 0.50
Nodes (4): date, get, Search the vault index. Returns SearchResult objects merged by hybrid RRF (when…, search_index()

### Community 101 - "Spend Tracking Reset"
Cohesion: 0.50
Nodes (4): Reset daily/monthly spend tracking (called at day boundary)., Reset spend tracking if a new day/month has started., _reset_spend_if_needed(), reset_spend_tracking()

### Community 106 - "test_agent fragment 106"
Cohesion: 0.50
Nodes (3): Integration test: enqueue task → verify it appears in queue., Create a task, verify it's queued, check status., TestFullAgentCycle

### Community 108 - "icon-192 fragment 108"
Cohesion: 1.00
Nodes (3): PWA Icon 192px (solid yellow square), PWA Icon 512px (solid yellow square), Sunny Yellow Brand Color

## Ambiguous Edges - Review These
- `get_page_3 tool (agent-synthesized)` → `Agent test tools leaked into live registry`  [AMBIGUOUS]
  vault/tools/registry.yaml · relation: conceptually_related_to
- `registry_test_tool tool (agent-synthesized)` → `Agent test tools leaked into live registry`  [AMBIGUOUS]
  vault/tools/registry.yaml · relation: conceptually_related_to

## Knowledge Gaps
- **83 isolated node(s):** `sunny`, `name`, `version`, `private`, `type` (+78 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `get_page_3 tool (agent-synthesized)` and `Agent test tools leaked into live registry`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `registry_test_tool tool (agent-synthesized)` and `Agent test tools leaked into live registry`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `get_settings()` connect `Settings & Config` to `App Startup & Lifespan`, `Projects Service Core`, `Index File Watcher`, `Research Service`, `Agent Loop Execution`, `Auth & Login`, `Research Listing & Citations`, `Hybrid Search (RRF)`, `Agent Control API`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `create_app()` connect `App Startup & Lifespan` to `Health Endpoint`, `Extraction Test Fixtures`, `Research API Tests`, `Settings & Config`, `Agent Test Fixtures`, `External Edit Preservation`, `Login Rate Limiting`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Why does `RulesParser` connect `Extraction Rules Parser` to `Vault Frontmatter & Atomic IO`, `Rules Hot Reload`, `Close Hook Extraction Tests`, `Extraction Logging & Hot Reload`, `Rules Engine & Fact Writes`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `SleepStateMachine` (e.g. with `AgentLoop` and `TestSleepStateMachine`) actually correct?**
  _`SleepStateMachine` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 24 inferred relationships involving `RulesEngine` (e.g. with `RulesHotReload` and `TestAllStarterRules`) actually correct?**
  _`RulesEngine` has 24 INFERRED edges - model-reasoned connections that need verification._