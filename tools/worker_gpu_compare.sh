#!/usr/bin/env bash
# worker_gpu_compare.sh — Étude comparative Whisper : transcrit la même liste
# d'épisodes avec deux modèles (medium puis large-v3) pour mesurer l'impact
# du modèle sur la qualité de l'extraction de recos.
#
# Sortie :
#   ~/transcripts/un-bon-moment-medium/<guid>.txt
#   ~/transcripts/un-bon-moment-large-v3/<guid>.txt
# Exposées via python -m http.server 8002 à la racine ~/transcripts/.
#
# Usage : bash worker_gpu_compare.sh [http://<main_ip>:8001]
set -e

MAIN_URL="${1:-http://192.168.1.58:8001}"
SOURCE="un-bon-moment"
WORK="$HOME/wc_tmp"
mkdir -p "$WORK"

source ~/wh/bin/activate 2>/dev/null || true
WHISPER_BIN="$HOME/whisper.cpp/build/bin/whisper-cli"
MODELS_DIR="$HOME/whisper.cpp/models"

# Récupère le dispatch comparison + la liste de guids.
echo "== Récupération du dispatch comparison depuis $MAIN_URL =="
curl -s -f -o "$WORK/episodes.json" "$MAIN_URL/dispatch/whisper_compare_episodes.json"
curl -s -f -o "$WORK/guids.txt"     "$MAIN_URL/dispatch/whisper_compare_guids.txt"
sed -i 's/\r$//' "$WORK/guids.txt" 2>/dev/null || true
N=$(grep -c . "$WORK/guids.txt")
echo "   $N épisode(s) à comparer"

# Télécharge ggml-medium / large-v3 si absent.
for M in medium large-v3; do
  if [ ! -f "$MODELS_DIR/ggml-$M.bin" ]; then
    echo "== Téléchargement du modèle ggml-$M.bin =="
    ( cd "$HOME/whisper.cpp" && bash ./models/download-ggml-model.sh "$M" )
  fi
done

# Serveur HTTP racine ~/transcripts/ (couvre les sous-dossiers -medium / -large-v3).
if ! pgrep -f "http.server 8002" >/dev/null; then
  echo "== Démarrage serveur transcripts sur :8002 =="
  ( cd "$HOME/transcripts" && nohup python -m http.server 8002 >/tmp/transcripts_server.log 2>&1 & )
fi

# Itère (modèle × épisode). large-v3 en dernier (plus lent).
for MODEL in medium large-v3; do
  OUT_DIR="$HOME/transcripts/$SOURCE-$MODEL"
  mkdir -p "$OUT_DIR"
  echo ""
  echo "########################################"
  echo "## Modèle : $MODEL"
  echo "########################################"
  i=0
  while IFS= read -r GUID <&3; do
    i=$((i+1))
    [ -z "$GUID" ] && continue
    OUT="$OUT_DIR/$GUID.txt"
    if [ -s "$OUT" ]; then
      echo "[$i/$N] $GUID — déjà transcrit ($MODEL), skip"
      continue
    fi
    URL=$(python3 -c "import json;print(json.load(open('$WORK/episodes.json'))['$GUID']['youtubeUrl'])")
    TITLE=$(python3 -c "import json;print(json.load(open('$WORK/episodes.json'))['$GUID']['title'][:50])")
    echo ""
    echo "[$i/$N] $TITLE ($GUID) — $MODEL"

    echo "-- 1/4 download YouTube audio (yt-dlp) --"
    rm -f "$WORK/cur".*
    if ! yt-dlp -f 'ba/b' -x --audio-format mp3 --audio-quality 0 \
         -o "$WORK/cur.%(ext)s" --no-progress "$URL" </dev/null; then
      echo "   ✗ échec yt-dlp, skip"
      continue
    fi
    if [ ! -f "$WORK/cur.mp3" ]; then
      echo "   ✗ pas de fichier mp3 issu de yt-dlp, skip"
      continue
    fi
    echo "   OK ($(du -h $WORK/cur.mp3 | cut -f1))"

    echo "-- 2/4 ffmpeg wav 16k --"
    ffmpeg -nostdin -y -loglevel error -i "$WORK/cur.mp3" -ar 16000 -ac 1 "$WORK/cur.wav" </dev/null

    echo "-- 3/4 whisper-cli (GPU, model=$MODEL) --"
    "$WHISPER_BIN" -m "$MODELS_DIR/ggml-$MODEL.bin" -l fr -oj -of "$WORK/cur" "$WORK/cur.wav" </dev/null

    echo "-- 4/4 JSON -> txt --"
    GUID="$GUID" OUT="$OUT" python3 - <<'PY'
import json, os
guid = os.environ["GUID"]; out = os.environ["OUT"]
json_path = os.path.expanduser("~/wc_tmp/cur.json")
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
  done 3< "$WORK/guids.txt"
done

echo ""
echo "=== TERMINÉ ==="
echo "Sortie :"
ls -lh "$HOME/transcripts/$SOURCE-medium/"     | tail -n 10
ls -lh "$HOME/transcripts/$SOURCE-large-v3/"   | tail -n 10
echo ""
echo "Rapatriement depuis la machine principale :"
echo "  bash tools/pull_transcripts_compare.sh [http://<laptop_ip>:8002]"
