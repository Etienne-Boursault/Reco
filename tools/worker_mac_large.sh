#!/usr/bin/env bash
# worker_mac_large.sh — Worker Mac M4 (Metal) pour large-v3-turbo.
#
# Sortie : ~/transcripts/un-bon-moment-large-v3-turbo/<guid>.txt
# Servie sur :8003 pour rapatriement par la machine principale.
#
# Idempotent : skip si le .txt existe déjà.
# Resume : il suffit de relancer pour reprendre où on s'est arrêté.
#
# Usage : bash worker_mac_large.sh [http://<main_ip>:8001]
set -e

MAIN_URL="${1:-http://192.168.1.58:8001}"
SOURCE="un-bon-moment"
MODEL="large-v3-turbo"
OUT_DIR="$HOME/transcripts/$SOURCE-$MODEL"
WORK="$HOME/wm_tmp"
LOG="$HOME/wm_compare.log"
mkdir -p "$OUT_DIR" "$WORK"

# Homebrew paths Apple Silicon
export PATH="/opt/homebrew/bin:$PATH"
WHISPER_BIN="/opt/homebrew/bin/whisper-cli"
MODELS_DIR="$HOME/whisper-models"
MODEL_BIN="$MODELS_DIR/ggml-$MODEL.bin"
mkdir -p "$MODELS_DIR"

# Empêche le Mac de s'endormir pendant la transcription (caffeinate).
# -i : système ne va pas en veille, -d : écran reste éveillé.
CAFFEINATE="/usr/bin/caffeinate -i -m"

# Récupère le dispatch + la liste de guids triés (oldest → newest pour le Mac
# afin de croiser le portable qui fait newest → oldest).
echo "== Récupération du dispatch depuis $MAIN_URL =="
curl -s -f -o "$WORK/episodes.json" "$MAIN_URL/dispatch/whisper_large_episodes.json"
curl -s -f -o "$WORK/guids.txt"     "$MAIN_URL/dispatch/whisper_mac_guids.txt"
N=$(grep -c . "$WORK/guids.txt")
echo "   $N épisode(s) dans la liste Mac (plus vieux en premier)"

if [ ! -f "$MODEL_BIN" ]; then
  echo "== Téléchargement du modèle $MODEL =="
  curl -L --fail -o "$MODEL_BIN" \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$MODEL.bin"
fi

# Serveur HTTP racine ~/transcripts/ pour rapatriement par le main (port 8003).
if ! pgrep -f "http.server 8003" >/dev/null; then
  echo "== Démarrage serveur transcripts sur :8003 =="
  ( cd "$HOME/transcripts" && nohup python3 -m http.server 8003 \
      > /tmp/transcripts_server_mac.log 2>&1 & )
fi

i=0
while IFS= read -r GUID <&3; do
  i=$((i+1))
  GUID="${GUID%$'\r'}"  # strip CR Windows
  GUID="${GUID%$'\n'}"
  [ -z "$GUID" ] && continue
  OUT="$OUT_DIR/$GUID.txt"
  if [ -s "$OUT" ]; then
    echo "[$i/$N] $GUID — déjà transcrit, skip"
    continue
  fi
  URL=$(GUID="$GUID" WORK="$WORK" python3 -c "import json,os;d=json.load(open(os.environ['WORK']+'/episodes.json'));g=os.environ['GUID'];print(d.get(g,{}).get('youtubeUrl',''))")
  if [ -z "$URL" ]; then
    echo "   ✗ guid '$GUID' absent du dispatch (URL vide)"
    continue
  fi
  TITLE=$(GUID="$GUID" WORK="$WORK" python3 -c "import json,os;d=json.load(open(os.environ['WORK']+'/episodes.json'));print(d.get(os.environ['GUID'],{}).get('title','')[:60])")
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

  echo "-- 3/4 whisper-cli (Metal, $MODEL) --"
  T0=$(date +%s)
  $CAFFEINATE "$WHISPER_BIN" -m "$MODEL_BIN" -l fr -oj -of "$WORK/cur" "$WORK/cur.wav" </dev/null
  echo "   ⏱  $(($(date +%s)-T0))s"

  echo "-- 4/4 JSON → txt --"
  GUID="$GUID" OUT="$OUT" python3 - <<'PY'
import json, os
guid = os.environ["GUID"]; out = os.environ["OUT"]
json_path = os.path.expanduser("~/wm_tmp/cur.json")
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

echo ""
echo "=== TERMINÉ ==="
echo "Transcripts produits : $(ls $OUT_DIR/*.txt 2>/dev/null | wc -l) / $N"
