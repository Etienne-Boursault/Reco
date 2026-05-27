#!/usr/bin/env bash
# brout_gpu.sh — Transcrire l'épisode « avec l'équipe de Brout » sur le portable
# (whisper.cpp + CUDA, depuis l'audio Acast direct, sans YouTube).
set -e

GUID=633b2f213ca1cc001201a69f
URL="https://sphinx.acast.com/p/acast/s/un-bon-moment/e/${GUID}/media.mp3"
TRANS_DIR="$HOME/transcripts/un-bon-moment"
WHISPER_BIN="$HOME/whisper.cpp/build/bin/whisper-cli"
MODEL="$HOME/whisper.cpp/models/ggml-small.bin"

mkdir -p "$TRANS_DIR"

echo "== 1/4 Téléchargement audio Acast =="
curl -fsSL -A "Mozilla/5.0" -o /tmp/brout.mp3 "$URL"
echo "   OK ($(du -h /tmp/brout.mp3 | cut -f1))"

echo "== 2/4 Conversion WAV 16 kHz =="
ffmpeg -nostdin -y -loglevel error -i /tmp/brout.mp3 -ar 16000 -ac 1 /tmp/brout.wav

echo "== 3/4 Transcription whisper.cpp (GPU) =="
"$WHISPER_BIN" -m "$MODEL" -l fr -oj -of /tmp/brout /tmp/brout.wav </dev/null

echo "== 4/4 Conversion JSON -> txt =="
GUID="$GUID" TRANS_DIR="$TRANS_DIR" python3 - <<'PY'
import json, os
guid = os.environ["GUID"]; trans_dir = os.environ["TRANS_DIR"]
data = json.load(open("/tmp/brout.json", encoding="utf-8", errors="replace"))
lines = []
for t in data.get("transcription", []):
    ms = t["offsets"]["from"]; s = ms // 1000
    h, rem = divmod(s, 3600); m, ss = divmod(rem, 60)
    lines.append(f"[{h:02d}:{m:02d}:{ss:02d}] {t['text'].strip()}")
open(f"{trans_dir}/{guid}.txt", "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("OK", len(lines), "segments")
PY

echo "DONE — transcrit dans $TRANS_DIR/$GUID.txt"
