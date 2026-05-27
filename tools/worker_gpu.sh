#!/usr/bin/env bash
# worker_gpu.sh — Worker GPU pour le portable (Ubuntu + GTX 950M).
#
# Récupère la liste d'épisodes assignée et le mapping guid->URL sur la machine
# principale, transcrit avec whisper.cpp+CUDA, sauvegarde chaque transcription
# dans ~/transcripts/un-bon-moment/<guid>.txt et la sert sur :8002 pour que la
# machine principale puisse les rapatrier.
#
# Usage : bash worker_gpu.sh [http://<main_ip>:8001]
set -e

MAIN_URL="${1:-http://192.168.1.58:8001}"
SOURCE="un-bon-moment"
TRANS_DIR="$HOME/transcripts/$SOURCE"
mkdir -p "$TRANS_DIR"

# Active venv + chemins (yt-dlp, deno) et binaires whisper.cpp.
source ~/wh/bin/activate
export PATH="$HOME/.deno/bin:$PATH"
WHISPER_BIN="$HOME/whisper.cpp/build/bin/whisper-cli"
MODEL="$HOME/whisper.cpp/models/ggml-small.bin"

echo "== Récupération du dispatch depuis $MAIN_URL =="
curl -s -f -o ~/laptop_guids.txt "$MAIN_URL/dispatch/laptop_guids.txt"
curl -s -f -o ~/episodes.json    "$MAIN_URL/dispatch/episodes.json"

# Serveur HTTP pour exposer les transcripts à la machine principale (port 8002).
if ! pgrep -f "http.server 8002" >/dev/null; then
  echo "== Démarrage serveur transcripts sur :8002 (rapatriement par main) =="
  ( cd "$TRANS_DIR" && nohup python -m http.server 8002 >/tmp/transcripts_server.log 2>&1 & )
fi

# Normalise les fins de ligne du fichier (au cas où il aurait du CRLF).
sed -i 's/\r$//' ~/laptop_guids.txt 2>/dev/null || true

TOTAL=$(grep -c . ~/laptop_guids.txt)
i=0
# IMPORTANT : on lit la liste sur le descripteur 3, pas sur stdin (0). Sinon
# ffmpeg/yt-dlp héritent du fichier en stdin et interprètent les guids comme
# des commandes interactives (« Enter command: … »).
while IFS= read -r -u 3 GUID; do
  GUID="${GUID%$'\r'}"          # ceinture + bretelles : retire un CR éventuel
  [ -z "$GUID" ] && continue
  i=$((i+1))
  OUT="$TRANS_DIR/$GUID.txt"
  if curl -s -f -I "$MAIN_URL/output/transcripts/$SOURCE/$GUID.txt" >/dev/null; then
    echo "[$i/$TOTAL] skip $GUID (main cache)"
    continue
  fi
  if [ -f "$OUT" ]; then
    echo "[$i/$TOTAL] skip $GUID (cache)"
    continue
  fi
  # Lookup URL+titre via stdin (immune aux caractères spéciaux dans GUID).
  read URL TITLE < <(printf '%s' "$GUID" | python -c '
import json, sys
g = sys.stdin.read().strip()
d = json.load(open("'"$HOME"'/episodes.json"))
ep = d.get(g, {})
url = ep.get("youtubeUrl", "")
title = ep.get("title", "?")[:60].replace(" ", "_")  # un seul mot pour read
print(url, title)
')
  if [ -z "$URL" ]; then
    echo "[$i/$TOTAL] ✗ pas d'URL pour $GUID — skip"
    continue
  fi
  echo "[$i/$TOTAL] $GUID — ${TITLE//_/ }"

  rm -f /tmp/clip.mp3 /tmp/clip.wav /tmp/clip.json
  if ! yt-dlp -q -x --audio-format mp3 -o /tmp/clip.mp3 "$URL" </dev/null; then
    echo "[$i/$TOTAL] ✗ yt-dlp a échoué — skip"
    continue
  fi
  ffmpeg -nostdin -y -loglevel error -i /tmp/clip.mp3 -ar 16000 -ac 1 /tmp/clip.wav </dev/null

  if ! "$WHISPER_BIN" -m "$MODEL" -l fr -oj -of /tmp/clip /tmp/clip.wav > /tmp/whisper.out 2>/tmp/whisper.err </dev/null; then
    echo "[$i/$TOTAL] ✗ whisper.cpp a échoué — voir /tmp/whisper.err"
    continue
  fi

  # Conversion JSON whisper.cpp -> format projet « [HH:MM:SS] texte »
python - "$OUT" <<'PY'
import json, sys
out_path = sys.argv[1]
data = json.load(open("/tmp/clip.json", encoding="utf-8", errors="replace"))
lines = []
for t in data.get("transcription", []):
    ms = t["offsets"]["from"]
    s = ms // 1000
    h, rem = divmod(s, 3600)
    m, ss = divmod(rem, 60)
    lines.append(f"[{h:02d}:{m:02d}:{ss:02d}] {t['text'].strip()}")
open(out_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
  echo "[$i/$TOTAL] ✓ $GUID"
done 3< ~/laptop_guids.txt
echo "Worker terminé. Transcripts dans $TRANS_DIR (servis sur :8002)."
