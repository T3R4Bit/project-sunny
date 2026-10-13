# Sunny V2

Keaton's single-user, self-hosted personal assistant: a FastAPI backend and a React PWA, running in Docker on the
M-700 (`sunshine-m700`). Notes live as markdown in a git-tracked vault that Syncthing mirrors to the PC.

- Spec: `docs/spec/SUNNY_V2_BUILD_PROMPT.md` (+ `SUNNY_V2_SECURITY.md`, which overrides its §23)
- App: <https://sunshine-m700.wahoo-sidewinder.ts.net> (tailnet only)

## What runs where

| Piece | Where | Reachable from |
| --- | --- | --- |
| `sunny` (API + PWA) | Docker on the M-700, `127.0.0.1:8080` | Tailnet over HTTPS via `tailscale serve` |
| `syncthing` | Docker on the M-700 | Sync port on the Tailscale IP only; GUI on `127.0.0.1:8384` |
| `nextcloud` + `nextcloud-db` | Off by default (`--profile calendar`) | `127.0.0.1:8082` |
| Vault copy | PC: `D:\projects\sunny-vault` (Syncthing folder `sunny-v2-vault`) | — |
| Desk display | Raspberry Pi `sunny-companion`, Chromium kiosk | — |

Data lives in the Docker volumes `sunny_sunny-vault` (the vault, with its `.git`), `sunny_sunny-state`
(SQLite DB, spend tracker, session-signing key) and `sunny_syncthing-config`. The Minecraft user units on the
same box are separate and untouched.

## Deploy / update (on the M-700, as `sunny`)

```bash
git clone https://github.com/T3R4Bit/Project-SUNNY ~/sunny   # first time
cd ~/sunny && git pull
cp ~/sunny-config/.env .env                                  # first time; .env is never committed
deploy/install.sh
```

`install.sh` builds and starts the stack, publishes it with `tailscale serve`, and installs the nightly backup
timer. It is safe to re-run.

### `.env`

Start from `.env.example`. The essentials are `CLAUDE_API_KEY`, `ADMIN_PASSWORD_HASH`, `TAILSCALE_IP` and
`TAILSCALE_HOSTNAME`. To set a new login password:

```bash
sudo docker compose run --rm --no-deps sunny python -m sunny.auth   # prints ADMIN_PASSWORD_HASH=...
# paste it into .env, then:
sudo docker compose up -d sunny
```

Spend caps (`LLM_SPEND_DAILY`, `LLM_SPEND_MONTHLY`, USD) are enforced before every Claude call and persist across
restarts. The Admin page shows current spend.

## Syncthing

The M-700's Syncthing shares the vault (minus `.git`, via `.stignore`) with `KEATON-PC` over Tailscale only.
Global discovery and relays are off. To add another device, open the GUI through an SSH tunnel:

```bash
ssh -L 8384:127.0.0.1:8384 sunny-lenovo    # then browse http://localhost:8384
```

Sync conflicts show up on the Admin page.

## Backups

`sunny-backup.timer` runs `deploy/backup.sh` nightly at 04:30. It writes a git bundle of the vault (full history),
a consistent copy of the SQLite DB, and the spend file to `/home/sunny/sunny-backups/`, keeping the last 14.
Restore notes are at the bottom of the script. Run one now with `sudo systemctl start sunny-backup`.

## Desk display (Pi)

On the Pi, once it is online: `bash deploy/pi-kiosk.sh`. It shows Sunny full-screen in Chromium under `cage` on
tty1. Log in once with a keyboard; sessions renew while in use.

## Reverting changes

Every vault write is a git commit inside the `sunny` container:

```bash
sudo docker exec sunny git -C /data/sunny-vault log --oneline | head
sudo docker exec sunny git -C /data/sunny-vault revert <commit>
```

## Development

```bash
pip install -e 'backend[dev]'
pytest                   # from the repo root; tests use tmp vaults, never the real one
cd frontend && npm ci && npm run dev
```

## Not wired up yet

The code for these exists but nothing calls it from an API route, the agent loop, or the UI:

- **Voice** (`tools/voice_pipeline.py`, `tools/wake_word.py`): no endpoint or UI. Optional deps: `pip install 'backend[voice]'`.
- **Calendar / Nextcloud** (`tools/caldav_sync.py`, `tools/calendar_tools.py`) and **Garmin** (`tools/garmin_sync.py`): never instantiated, and the settings are never read.
- **Semantic search** (`index/vector.py`): nothing writes embeddings, so search is keyword-only (FTS5).
- **Chat tools** (`llm/tools.py`): the registry exists, but tools are not passed to Claude.
- **Push notifications**: no VAPID keys and no sender.

## Lab build history

V2 was built by an agent on the KSU AI Lab DGX. The lab tooling (`lab/`, `setup.sh`, `push_checkpoint.sh`,
`teardown.sh`, `.clinerules`, `AGENTS.md`) and its working state (`PROGRESS.md`, `DECISIONS.md`, `BLOCKERS.md`)
are kept for reference.
