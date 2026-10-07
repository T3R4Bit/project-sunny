# Sunny V2

Single-user, self-hosted personal assistant. The full specification is in `docs/spec/SUNNY_V2_BUILD_PROMPT.md`, and the security addendum in `docs/spec/SUNNY_V2_SECURITY.md` overrides §23 of it. This repo starts with only the spec and the lab tooling; a coding agent builds the code by working through the phases.

The coding agent rewrites this README in phase P14 with the deploy steps for the M-700.

---

## Lab build: KSU AI Lab DGX

### 1. Clone (on the DGX)

In the DGX browser, sign in to GitHub and create a **fine-grained token** with these settings:

- Repository access: only this repo
- Permissions: Contents read/write
- Expiration: 7 days

Then sign out of GitHub in the browser and run:

```bash
mkdir -p ~/lab && cd ~/lab
git config --global user.name  "Keaton"
git config --global user.email "<id>+<username>@users.noreply.github.com"
git config --global credential.helper 'cache --timeout=604800'
git clone https://github.com/<you>/sunny.git && cd sunny     # paste the token as the password
```

### 2. Setup

```bash
./setup.sh
```

The script does the rest:

- checks the machine (GPU, docker access, disk space, network)
- starts the model download
- builds the sandbox container
- fetches the speech, embedding and voice-detection models
- waits until the model answers
- prints the Cline settings and the first prompt

You can safely re-run it.

If the vLLM container crashes on the GB10, rerun with NVIDIA's build. Pick a tag that supports the driver version the script printed:

```bash
VLLM_IMAGE=nvcr.io/nvidia/vllm:<tag>-py3 ./setup.sh
```

### 3. Agent

Install VS Code on the DGX. Without sudo, use the ARM64 `.tar.gz` from code.visualstudio.com and run it from its extracted folder. Then install the Cline extension, open `~/lab/sunny`, and enter the settings that `setup.sh` printed. Paste the first prompt.

### 4. During the week / end of week

```bash
./push_checkpoint.sh   # commit + push everything
./teardown.sh          # last day: push, stop containers, remove git credentials
```

When you're done, delete the token on GitHub.

### Layout

| Path | What |
|---|---|
| `docs/spec/` | Spec, security addendum, `LAB_RUN.md` (agent's lab rules) |
| `lab/` | Lab infrastructure: vLLM + sandbox compose, Dockerfile, model fetch. The agent never edits it. |
| `.clinerules` | Auto-loaded by Cline; points the agent at `LAB_RUN.md` |
| `PROGRESS.md` `DECISIONS.md` `BLOCKERS.md` | The agent's working state |
