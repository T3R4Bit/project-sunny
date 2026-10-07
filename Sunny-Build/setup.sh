#!/usr/bin/env bash
# One-shot lab setup for the Sunny V2 build on the KSU AI Lab DGX.
# Run on the DGX itself, from the repo root, after cloning:   ./setup.sh
# Safe to re-run: every step skips what's already done.
#
# Options (environment variables):
#   VLLM_IMAGE=nvcr.io/nvidia/vllm:<tag>-py3   use NVIDIA's vLLM build instead of upstream
#   NO_WAIT=1                                  don't wait for the model to finish loading
#   SKIP_PREFLIGHT=1                           skip machine checks

set -uo pipefail
cd "$(dirname "$0")"
REPO="$(pwd)"
LAB="$REPO/lab"
MODELS="$HOME/lab-cache/models"

c_ok()   { printf '\033[32m  ok\033[0m  %s\n' "$*"; }
c_warn() { printf '\033[33mwarn\033[0m  %s\n' "$*"; }
c_fail() { printf '\033[31mFAIL\033[0m  %s\n' "$*"; exit 1; }
step()   { printf '\n\033[1m== %s\033[0m\n' "$*"; }

dc() { (cd "$LAB" && docker compose "$@"); }

# ---------------------------------------------------------------- 1. preflight
if [ "${SKIP_PREFLIGHT:-0}" != "1" ]; then
  step "1/7 Preflight"
  [ "$(uname -m)" = "aarch64" ] && c_ok "arch aarch64" || c_warn "arch is $(uname -m), expected aarch64"

  command -v nvidia-smi >/dev/null || c_fail "nvidia-smi not found"
  DRIVER="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)"
  c_ok "GPU driver ${DRIVER:-unknown}"

  command -v docker >/dev/null || c_fail "docker not found"
  docker info >/dev/null 2>&1 || c_fail "cannot talk to docker. Is your user in the 'docker' group? (groups: $(groups)). Ask the lab admin."
  docker compose version >/dev/null 2>&1 || c_fail "docker compose plugin missing"
  c_ok "docker + compose"

  if docker run --rm --gpus all ubuntu:22.04 nvidia-smi -L >/dev/null 2>&1; then
    c_ok "GPU visible inside containers"
  else
    c_fail "containers cannot see the GPU (nvidia container toolkit). Ask the lab admin."
  fi

  FREE_GB=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc '0-9')
  [ "${FREE_GB:-0}" -ge 60 ] && c_ok "${FREE_GB} GB free" || c_warn "only ${FREE_GB} GB free in \$HOME; model + images need ~60 GB"

  for u in https://huggingface.co https://pypi.org https://registry.npmjs.org https://github.com; do
    if curl -s -o /dev/null --max-time 10 "$u"; then c_ok "reach $u"; else c_fail "cannot reach $u (lab network block?)"; fi
  done

  git -C "$REPO" remote get-url origin >/dev/null 2>&1 && c_ok "git remote: $(git -C "$REPO" remote get-url origin)" \
    || c_warn "no git remote 'origin'; push_checkpoint.sh will fail until it exists"
fi

# ---------------------------------------------------------------- 2. local prep
step "2/7 Local prep"
mkdir -p "$MODELS" "$HOME/.cache/huggingface"
printf "UID=%s\nGID=%s\n" "$(id -u)" "$(id -g)" > "$LAB/.env"
[ -n "${VLLM_IMAGE:-}" ] && echo "VLLM_IMAGE=$VLLM_IMAGE" >> "$LAB/.env"
chmod +x "$REPO/push_checkpoint.sh" "$REPO/teardown.sh" "$LAB/fetch_models.sh"
git -C "$REPO" config core.fileMode false
c_ok "folders, lab/.env, permissions"

# ---------------------------------------------------------------- 3. inference (starts the big download)
step "3/7 Start inference engine (Qwen3.6-35B-A3B-FP8, ~35-40 GB first download)"
dc up -d inference-engine || c_fail "inference-engine failed to start"
c_ok "sunny-qwen-engine started; download/load continues in the background"

# ---------------------------------------------------------------- 4. sandbox image
step "4/7 Build sandbox image"
dc build sunny-sandbox || c_fail "sandbox build failed"
c_ok "sandbox image built"

# ---------------------------------------------------------------- 5. small models
step "5/7 Fetch runtime models (embeddings, whisper, piper, vosk, silero)"
if [ -d "$MODELS/vosk" ] && [ -d "$MODELS/piper" ] && [ -f "$MODELS/silero/silero_vad.onnx" ] \
   && [ -d "$MODELS/faster-whisper-small.en" ] && [ -d "$MODELS/fastembed" ]; then
  c_ok "already present"
else
  dc run --rm --no-deps -v "$MODELS:/out" sunny-sandbox bash lab/fetch_models.sh || c_fail "model fetch failed"
  c_ok "models in $MODELS"
fi

# ---------------------------------------------------------------- 6. sandbox up + verify
step "6/7 Start sandbox"
dc up -d sunny-sandbox || c_fail "sandbox failed to start"
docker exec sunny-sandbox bash -c 'python --version && node --version && git --version && tesseract --version | head -1 && whoami' \
  && c_ok "sandbox tools" || c_fail "sandbox check failed"
[ "$(docker exec sunny-sandbox ls /models | wc -l)" -ge 5 ] && c_ok "/models mounted" || c_warn "/models looks incomplete"

# ---------------------------------------------------------------- 7. wait for model
step "7/7 Inference engine"
if [ "${NO_WAIT:-0}" = "1" ]; then
  c_warn "NO_WAIT=1: not waiting. Check later with: curl -s localhost:8000/v1/models"
else
  echo "  waiting for http://localhost:8000 (up to 90 min; Ctrl-C is safe, it keeps loading)"
  for i in $(seq 1 540); do
    if curl -sf localhost:8000/v1/models >/dev/null; then break; fi
    state="$(docker inspect -f '{{.State.Status}}' sunny-qwen-engine 2>/dev/null)"
    if [ "$state" != "running" ]; then
      echo; docker logs --tail 40 sunny-qwen-engine
      c_fail "inference container is '$state'. If this is an arch/CUDA error, rerun with:  VLLM_IMAGE=nvcr.io/nvidia/vllm:<tag>-py3 ./setup.sh"
    fi
    [ $((i % 6)) -eq 0 ] && printf '  %3d min  %s\n' $((i/6)) "$(docker logs --tail 1 sunny-qwen-engine 2>&1 | cut -c1-100)"
    sleep 10
  done
  REPLY_TXT="$(curl -s localhost:8000/v1/chat/completions -H 'Content-Type: application/json' \
    -d '{"model":"qwen3.6","messages":[{"role":"user","content":"Reply with the single word READY."}],"max_tokens":200}' \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["choices"][0]["message"]["content"])' 2>/dev/null)"
  [ -n "$REPLY_TXT" ] && c_ok "model answered: $(echo "$REPLY_TXT" | tail -1 | cut -c1-60)" || c_warn "model not answering yet"
fi

cat <<'EOF'

== Setup complete. Next:

Cline (VS Code > Cline settings)
  Provider        OpenAI Compatible
  Base URL        http://localhost:8000/v1
  API key         none
  Model ID        qwen3.6
  Context window  131072
  .clinerules in the repo root loads automatically.

First prompt to paste into Cline:
  Read docs/spec/LAB_RUN.md, then docs/spec/SUNNY_V2_BUILD_PROMPT.md and
  docs/spec/SUNNY_V2_SECURITY.md in full. Then follow PROGRESS.md, starting at P0.

Every new task / restart:
  Read docs/spec/LAB_RUN.md, then PROGRESS.md. Continue from the first unchecked item.

Checkpoint any time:  ./push_checkpoint.sh
End of week:          ./teardown.sh
EOF
