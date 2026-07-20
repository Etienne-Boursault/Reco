#!/usr/bin/env bash
# worker_gpu_large.sh — Re-transcription large-v3 depuis YouTube, batches de 5.
#
# Lit la liste de guids triée (plus récent en tête) depuis la machine principale,
# télécharge l'audio YouTube (yt-dlp), transcrit avec whisper.cpp + CUDA en
# large-v3, écrit dans ~/transcripts/un-bon-moment-large-v3/<guid>.txt et
# expose sur :8002 pour que le main rapatrie + extraie au fil de l'eau.
#
# Idempotent : skip si le .txt existe déjà.
#
# Usage : bash worker_gpu_large.sh [http://<main_ip>:8001]
set -e

MAIN_URL="${1:-http://192.168.1.58:8001}"
SOURCE="un-bon-moment"
MODEL="large-v3-turbo"
OUT_DIR="$HOME/transcripts/$SOURCE-$MODEL"
WORK="$HOME/wl_tmp"
LOG="$HOME/wl_compare.log"
mkdir -p "$OUT_DIR" "$WORK"

source ~/wh/bin/activate 2>/dev/null || true
WHISPER_BIN="$HOME/whisper.cpp/build/bin/whisper-cli"
MODEL_BIN="$HOME/whisper.cpp/models/ggml-$MODEL.bin"

# Récupère le dispatch + la liste de guids triés (recent → old).
echo "== Récupération du dispatch depuis $MAIN_URL =="
curl -s -f -o "$WORK/episodes.json" "$MAIN_URL/dispatch/whisper_large_episodes.json"
curl -s -f -o "$WORK/guids.txt"     "$MAIN_URL/dispatch/whisper_large_guids.txt"
sed -i 's/\r$//' "$WORK/guids.txt" 2>/dev/null || true
N=$(grep -c . "$WORK/guids.txt")
echo "   $N épisode(s) à traiter (large-v3, plus récents en premier)"

if [ ! -f "$MODEL_BIN" ]; then
  echo "== Téléchargement du modèle $MODEL =="
  ( cd "$HOME/whisper.cpp" && bash ./models/download-ggml-model.sh "$MODEL" )
fi

# Serveur HTTP racine ~/transcripts/ pour rapatriement par le main.
if ! pgrep -f "http.server 8002" >/dev/null; then
  echo "== Démarrage serveur transcripts sur :8002 =="
  ( cd "$HOME/transcripts" && nohup python -m http.server 8002 >/tmp/transcripts_server.log 2>&1 & )
fi

i=0
BATCH=5
while IFS= read -r GUID <&3; do
  i=$((i+1))
  [ -z "$GUID" ] && continue
  OUT="$OUT_DIR/$GUID.txt"
  if [ -s "$OUT" ]; then
    echo "[$i/$N] $GUID — déjà transcrit, skip"
    continue
  fi
  URL=$(python3 -c "import json;print(json.load(open('$WORK/episodes.json'))['$GUID']['youtubeUrl'])")
  TITLE=$(python3 -c "import json;print(json.load(open('$WORK/episodes.json'))['$GUID']['title'][:60])")
  echo ""
  echo "########## [$i/$N] $TITLE ($GUID) ##########"

  echo "-- 1/4 yt-dlp → audio mp3 --"
  rm -f "$WORK/cur".*
  if ! yt-dlp -f 'ba/b' -x --audio-format mp3 --audio-quality 0 \
       -o "$WORK/cur.%(ext)s" --no-progress "$URL" </dev/null; then
    echo "   ✗ échec yt-dlp, skip"
    continue
  fi
  [ -f "$WORK/cur.mp3" ] || { echo "   ✗ mp3 absent, skip" ; continue ; }
  echo "   OK ($(du -h $WORK/cur.mp3 | cut -f1))"

  echo "-- 2/4 ffmpeg wav 16k mono --"
  ffmpeg -nostdin -y -loglevel error -i "$WORK/cur.mp3" -ar 16000 -ac 1 "$WORK/cur.wav" </dev/null

  echo "-- 3/4 whisper-cli ($MODEL) --"
  T0=$(date +%s)
  "$WHISPER_BIN" -m "$MODEL_BIN" -l fr -oj -of "$WORK/cur" "$WORK/cur.wav" </dev/null
  echo "   ⏱  $(($(date +%s)-T0))s"

  echo "-- 4/4 JSON → txt --"
  GUID="$GUID" OUT="$OUT" python3 - <<'PY'
import json, os
guid = os.environ["GUID"]; out = os.environ["OUT"]
json_path = os.path.expanduser("~/wl_tmp/cur.json")
data = json.load(open(json_path, encoding="utf-8", errors="replace"))
lines = []
for t in data.get("transcription", []):
    ms = t["offsets"]["from"]; s = ms // 1000
    h, rem = divmod(s, 3600); m, ss = divmod(rem, 60)
    lines.append(f"[{h:02d}:{m:02d}:{ss:02d}] {t['text'].strip()}")
open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"   OK {len(lines)} segments -> {out}")
PY

  rm -f "$WORK/cur.mp3" "$WORK/cur.wav" "$WORK/cur.json"

  # Marqueur fin de batch — le main peut rapatrier+extraire ici.
  if [ $((i % BATCH)) -eq 0 ]; then
    echo ""
    echo ">>> BATCH $((i / BATCH))/$((N / BATCH + 1)) terminé. Total transcrits : $(ls $OUT_DIR/*.txt | wc -l) <<<"
  fi
done 3< "$WORK/guids.txt"

echo ""
echo "=== TERMINÉ ==="
echo "Transcripts produits : $(ls $OUT_DIR/*.txt | wc -l) / $N"
