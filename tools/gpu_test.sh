#!/usr/bin/env bash
# gpu_test.sh — Benchmark faster-whisper sur GPU (Ubuntu / GTX 950M).
# La GTX 950M (Maxwell) ne supporte QUE float32. yt-dlp a besoin de deno.
#
# Usage : bash gpu_test.sh ["<url youtube>"]
set -e

VIDEO="${1:-https://www.youtube.com/watch?v=Uo_03B3Q8Ag}"

echo "== 1/6 Paquets système =="
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv ffmpeg curl

echo "== 2/6 Runtime JS (deno) pour yt-dlp =="
if ! command -v deno >/dev/null 2>&1; then curl -fsSL https://deno.land/install.sh | sh; fi
export PATH="$HOME/.deno/bin:$PATH"

echo "== 3/6 Env Python + faster-whisper + libs CUDA =="
python3 -m venv ~/wh
source ~/wh/bin/activate
pip install -q -U pip faster-whisper yt-dlp nvidia-cublas-cu12 nvidia-cudnn-cu12

echo "== 4/6 Chemins cuDNN/cuBLAS (via find) =="
CUBLAS_DIR=$(dirname "$(find ~/wh -name 'libcublas.so*' | head -1)")
CUDNN_DIR=$(dirname "$(find ~/wh -name 'libcudnn.so*' | head -1)")
export LD_LIBRARY_PATH="$CUBLAS_DIR:$CUDNN_DIR:$LD_LIBRARY_PATH"
echo "   $LD_LIBRARY_PATH"

echo "== 5/6 Extrait de 5 min (si absent) =="
[ -f clip.mp3 ] || yt-dlp -q -x --audio-format mp3 --download-sections "*0-300" -o clip.mp3 "$VIDEO"
ls -la clip.mp3

echo "== 6/6 Benchmark GPU (float32) =="
python - <<'PY'
import time
from faster_whisper import WhisperModel
try:
    m = WhisperModel("small", device="cuda", compute_type="float32")
    t = time.time()
    segs, info = m.transcribe("clip.mp3", language="fr", vad_filter=True, beam_size=5)
    n = sum(1 for _ in segs)
    dt = time.time() - t
    print(f"\n>>> RESULTAT : OK float32 — 5 min audio en {dt:.0f}s — {300/dt:.1f}x temps reel — {n} segments\n")
except Exception as e:
    print(f"\n>>> ECHEC : {type(e).__name__}: {e}\n")
PY
