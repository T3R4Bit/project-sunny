# LAB RUN — read this before the build prompt

This file sets the environment rules for building Sunny V2 inside the KSU AI Lab. It takes priority over anything in `SUNNY_V2_BUILD_PROMPT.md` that conflicts with it.

## Read order

1. This file.
2. `docs/spec/SUNNY_V2_BUILD_PROMPT.md`: the full specification.
3. `docs/spec/SUNNY_V2_SECURITY.md`: replaces §23, amends §2 and §12.3. Where it conflicts with the build prompt, it wins.
4. `PROGRESS.md` (already seeded with the phase list). Start at the first unchecked item. Keep `DECISIONS.md` and `BLOCKERS.md` current as §0 describes.

## Machine

- NVIDIA DGX (GB10), **ARM64 / aarch64**, Ubuntu 22.04 base. Some Python wheels do not exist for aarch64. If a dependency won't install after 30 minutes of trying, stub it behind its interface, log it in `BLOCKERS.md` with the exact error, and move on. Piper, sqlite-vec and ctranslate2 are the most likely to cause trouble.
- The host disk is wiped at the end of the week. Work that isn't pushed to GitHub is lost.
- There is no Anthropic API key and there never will be one here. Every Claude call goes through the fake gateway.

## Where commands run

| What | Where | How |
|---|---|---|
| python, pip/uv, pytest, node, npm, ruff, any build or test | `sunny-sandbox` container | `docker exec -w /workspace sunny-sandbox <command>` |
| `git` (commit, push) | host, repo root | `./push_checkpoint.sh` |
| Sunny's own `docker compose` (P0 acceptance and later) | host, repo root | `docker compose -f docker-compose.yml up -d --build` |

- The repo is mounted at `/workspace` inside the sandbox, and the sandbox runs as the same uid as the host user.
- Pre-downloaded models live at `/models` inside the sandbox (read-only). Point fastembed, Vosk, faster-whisper, Piper and Silero at these paths through settings. Do not download them again.

## Do not touch

- `lab/`: the lab infrastructure (inference server and sandbox). Never edit it, start it or stop it.
- The `sunny-qwen-engine` container and port 8000. That's you. Stopping it ends the session.
- Ports reserved for the lab: 8000 (inference), 5173 (Vite dev server inside the sandbox), 8081 (uvicorn dev server inside the sandbox). Sunny's own `docker-compose.yml` publishes the app on host port 8080. Nextcloud and Syncthing go on ports above 9000.
- The host OS. No `sudo`, no `apt`, no global installs on the host.

## Checkpoints

- Run `./push_checkpoint.sh` from the host after every test module that passes and at the end of every phase. If the push fails, stop and write the error to `BLOCKERS.md`.
- Never commit `.env`, `.sunny/`, models, `node_modules/`, or build output. `.gitignore` already covers these. Don't weaken it.

## Pacing (one week, local model)

- Phases run in §24 order. If a phase's acceptance check still fails after 3 real attempts, record the failing check in `BLOCKERS.md`, mark the phase `partial` in `PROGRESS.md`, and move to the next phase.
- Must finish: P0–P4. Target: P5–P8. Stretch: P9–P14.
- Work in small tasks. At the start of every task, re-read `PROGRESS.md`. Before ending every task, update `PROGRESS.md` with what's done, what's next and any open failure. The next task starts with no memory beyond what's in the repo.
- Every test must pass offline. If a test needs the network, use a fake.

## Resume prompt

When a new agent task starts, the human pastes:

> Read docs/spec/LAB_RUN.md, then PROGRESS.md. Continue from the first unchecked item. Re-read the relevant spec sections before writing code.
