#!/usr/bin/env bash
# retranscribe_acast_gpu.sh — Re-transcrit en boucle une liste d'épisodes depuis
# l'audio Acast (User-Agent navigateur), avec whisper.cpp + CUDA.
# Liste = tools/dispatch/retranscribe.json (récupéré depuis le file server main).
set -e

MAIN_FILESERVER="http://192.168.1.219:8001"
TRANS_DIR="$HOME/transcripts/un-bon-moment"
WHISPER_BIN="$HOME/whisper.cpp/build/bin/whisper-cli"
MODEL="$HOME/whisper.cpp/models/ggml-small.bin"
WORK="$HOME/retr_tmp"

mkdir -p "$TRANS_DIR" "$WORK"

# 1) Récupérer la dispatch JSON
echo "== Récupération dispatch =="
curl -fsSL -o "$WORK/list.json" "$MAIN_FILESERVER/tools/dispatch/retranscribe.json"
N=$(python3 -c "import json;print(len(json.load(open('$WORK/list.json')))) ")
echo "   $N épisodes à traiter"

for i in $(seq 0 $((N-1))); do
  GUID=$(python3 -c "import json;d=json.load(open('$WORK/list.json'));print(d[$i]['guid'])")
  URL=$(python3 -c "import json;d=json.load(open('$WORK/list.json'));print(d[$i]['audioUrl'])")
  TITLE=$(python3 -c "import json;d=json.load(open('$WORK/list.json'));print(d[$i]['title'][:50])")
  OUT="$TRANS_DIR/$GUID.txt"

  echo ""
  echo "=== [$((i+1))/$N] $TITLE ($GUID) ==="

  if [ -s "$OUT" ]; then
    echo "   déjà transcrit, skip"
    continue
  fi

  echo "-- 1/4 download Acast --"
  if ! curl -fsSL -A "Mozilla/5.0" -o "$WORK/cur.mp3" "$URL"; then
    echo "   ✗ échec download, skip"
    continue
  fi
  echo "   OK ($(du -h $WORK/cur.mp3 | cut -f1))"

  echo "-- 2/4 ffmpeg wav 16k --"
  ffmpeg -nostdin -y -loglevel error -i "$WORK/cur.mp3" -ar 16000 -ac 1 "$WORK/cur.wav" </dev/null

  echo "-- 3/4 whisper-cli (GPU) --"
  "$WHISPER_BIN" -m "$MODEL" -l fr -oj -of "$WORK/cur" "$WORK/cur.wav" </dev/null

  echo "-- 4/4 JSON -> txt --"
  GUID="$GUID" OUT="$OUT" python3 - <<'PY'
import json, os
guid = os.environ["GUID"]; out = os.environ["OUT"]
data = json.load(open("/root/retr_tmp/cur.json", encoding="utf-8", errors="replace")) if os.path.exists("/root/retr_tmp/cur.json") else json.load(open(os.path.expanduser("~/retr_tmp/cur.json"), encoding="utf-8", errors="replace"))
lines = []
for t in data.get("transcription", []):
    ms = t["offsets"]["from"]; s = ms // 1000
    h, rem = divmod(s, 3600); m, ss = divmod(rem, 60)
    lines.append(f"[{h:02d}:{m:02d}:{ss:02d}] {t['text'].strip()}")
open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"   OK {len(lines)} segments -> {out}")
PY

  rm -f "$WORK/cur.mp3" "$WORK/cur.wav" "$WORK/cur.json"
done

echo ""
echo "=== TERMINÉ ==="
ls -lh "$TRANS_DIR" | tail -n 20
