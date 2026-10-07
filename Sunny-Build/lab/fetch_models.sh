#!/usr/bin/env bash
# Downloads the small runtime models Sunny needs into /out (= ~/lab-cache/models on the host).
# Run from the repo root on the host:
#   cd lab && docker compose run --rm -v ~/lab-cache/models:/out sunny-sandbox bash lab/fetch_models.sh
set -euo pipefail
OUT=/out
mkdir -p "$OUT"
pip install --user -q fastembed huggingface_hub

python - <<'PY'
import io, zipfile, urllib.request, pathlib
from huggingface_hub import snapshot_download, hf_hub_download
out = pathlib.Path("/out")

# Embeddings (fastembed, ONNX)
from fastembed import TextEmbedding
TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=str(out / "fastembed"))
print("ok  fastembed bge-small-en-v1.5")

# STT finals
snapshot_download("Systran/faster-whisper-small.en", local_dir=out / "faster-whisper-small.en")
print("ok  faster-whisper small.en")

# TTS voice
for f in ("en_US-lessac-medium.onnx", "en_US-lessac-medium.onnx.json"):
    hf_hub_download("rhasspy/piper-voices", f"en/en_US/lessac/medium/{f}", local_dir=out / "piper")
print("ok  piper en_US-lessac-medium")

# STT partials
url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url).read())).extractall(out / "vosk")
print("ok  vosk small en-us 0.15")

# VAD
vad = out / "silero" / "silero_vad.onnx"
vad.parent.mkdir(parents=True, exist_ok=True)
urllib.request.urlretrieve(
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx", vad)
print("ok  silero vad")
PY

find "$OUT" -maxdepth 2 | sort
