# SUNNY V2 — SECURITY ADDENDUM (replaces §23)

Design rule: spend security effort where an autonomous agent with private data, untrusted input, and outbound reach can do irreversible damage. Everything else stays cheap. Each item is tagged with its speed cost and the phase it lands in. Nothing here blocks P0–P5.

Threat model, in order of likelihood: (1) prompt injection through ingested content, (2) exposed or unpatched services, (3) supply-chain compromise of a dependency, (4) the agent exceeding its scope while chasing a goal. Sentient-AI scenarios are out of scope.

---

## A. Ship with P0 (cost: under 2 hours total, no ongoing drag)

1. **No public exposure.** No port forwards. Reach everything over Tailscale only. No Funnel. Tag the M-700 and restrict ACLs so only the PC and phone can reach Sunny, Nextcloud, and Syncthing.
2. **Container baseline** in `docker-compose.yml`: non-root user, `cap_drop: [ALL]`, `read_only: true` with explicit tmpfs and volume mounts, `no-new-privileges`, no `privileged`, never mount `docker.sock`.
3. **Secrets stay out of env where possible.** Claude key and OAuth tokens load from `.sunny/secrets/` files, not process environment (env vars were the OpenClaw leak path). Anthropic-side: dedicated workspace key with its own monthly limit, separate from any key used elsewhere.
4. **Login hardening:** password hash, rate limit and lockout on login, `SameSite=Strict` cookie, Origin check on `/ws/*` and all state-changing routes.
5. **ZFS snapshots** on the vault dataset with a retention hold, plus one off-box replica. Git is not a backup against an agent that can rewrite history.
6. **Dependency pinning:** lockfile with hashes, nothing installed at runtime.

## B. Ship with P5 (research ingest) (cost: about half a day)

7. **Shared fetch module** used by every extractor, agent tool, and pathfinder source. It resolves DNS itself, blocks private, loopback, link-local, and Tailscale ranges, caps response size and redirects, and re-checks after redirects. No extractor opens its own connections.
8. **Extractors run in a worker with no secrets mounted and no vault write access** beyond their own `sources/<id>/` output. PDF, OCR, and office-format parsers are the riskiest code in the build.
9. **GitHub ingest:** shallow clone with `core.hooksPath=/dev/null`, no submodules, never import or execute anything from the clone.
10. **Provenance tag.** Every chunk from an ingested source carries `trust: untrusted`. Prompt assembly wraps untrusted chunks in a delimited block with the instruction that it is data, not commands. Not a complete defense, but it raises the bar cheaply.

## C. Ship with P6 (agent) (cost: about one day, the main real cost)

11. **Real sandbox for synthesized tools.** Replace "subprocess with timeout" with a separate container or bubblewrap/gVisor jail: distinct uid, no network by default, read-only root, only the paths the tool declares mounted. Network access is a per-tool declared allowlist, reviewed on first run.
12. **Credential broker.** Google, Garmin, Spotify, and Nextcloud tokens live in a small separate process exposing narrow calls (`create_event`, `list_events`). The agent and tool workers never hold a token. This is what makes item 11 meaningful.
13. **Policy in code, not prompts.** Extend the `web_search` gating pattern to every tool: a table of `tool → allowed contexts → needs approval`. Enforced in the gateway.
14. **Side-effect approval.** Anything external and irreversible (send, calendar write to Google, new outbound domain, new synthesized tool's first network use) is SUGGEST tier. Git revert does not cover these.
15. **Memory write gate.** A session that touched untrusted content cannot write to `personal-context.md`, `memory/facts/`, or `docs/instructions/` without approval. Extraction gates (>0.85 auto) apply only to Keaton's own turns.
16. **Kill switch outside the agent's reach:** revoking the Tailscale tag, stopping the container from the PC, and the Anthropic-side spend limit. The agent process never has write access to any of these, and no shutdown logic lives in the vault.
17. **Canaries.** Plant fake credentials and a fake `secrets/` file in the vault and workers. Any read triggers an ALERT.

## D. Before first unattended sleep run (cost: small, gates only the overnight feature)

18. **Sleep-mode restrictions:** no new tool synthesis, no outbound writes, research fetches only through the shared fetch module with a domain allowlist per topic, hard cap on fetches per job.
19. **Off-box append-only log** of gateway calls, fetches, and tool executions. Review the first three sleep reports by hand.

## E. Defer (revisit if the threat changes)

- Full egress firewall at the router for the whole M-700.
- Separate host or VLAN for Warren (do it if Warren goes live with real funds; until then, separate Docker network and read-only status only).
- Formal prompt-injection classifier on ingest. Provenance tagging plus approvals covers most of the value.

---

## Changes to existing spec text

- §2 "No permission gates": amend to "No permission gates on vault edits. Gates exist on external side effects and memory writes from untrusted sessions (see C13–C15)."
- §12.3: replace the sandbox description with item 11.
- §23 bullet on token files: add "readable only by the credential broker".
- Sync: `.stignore` adds `tools/`.

## Acceptance checks

| Phase | Check |
|---|---|
| P0 | Compose file passes a script asserting non-root, dropped caps, no docker.sock mount. `nmap` from outside Tailscale shows nothing. Login lockout test passes. |
| P5 | Fetch module rejects `127.0.0.1`, `10.x`, `192.168.x`, and a redirect to either. Extractor worker cannot read `.sunny/secrets/`. |
| P6 | A synthesized tool that tries to read secrets, open a socket, or write outside its mounts fails and is logged. Agent process cannot read any token file. Canary read raises ALERT. Untrusted-session memory write is queued, not applied. |
| P8 | Simulated night with a poisoned fixture source makes no outbound call outside the allowlist and writes nothing to memory. |

## Speed budget

Sections A and B together are roughly one working day spread across P0 and P5. Section C is the only real schedule cost, about a day in P6, and it is what separates Sunny from the exposed-agent pattern seen in OpenClaw. Sections D and E are deferrable. If time is short, cut in this order: E, then 17, then 19. Do not cut 11, 12, 14, or 15.
