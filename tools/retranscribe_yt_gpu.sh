#!/usr/bin/env bash
# retranscribe_yt_gpu.sh — Re-transcrit en boucle une liste d'épisodes en
# téléchargeant l'AUDIO YOUTUBE (yt-dlp → mp3 → wav 16k mono → whisper.cpp/CUDA).
# Liste = tools/dispatch/retranscribe_yt.json (récupérée du file server main).
#
# Cible : aligner les timecodes du transcript avec la VIDÉO YouTube (les liens
# de relecture "?t=NNNs" pointent ainsi exactement au bon moment dans le player).
set -e

MAIN_FILESERVER="http://192.168.1.58:8001"
TRANS_DIR="$HOME/transcripts/un-bon-moment"
WHISPER_BIN="$HOME/whisper.cpp/build/bin/whisper-cli"
MODEL="$HOME/whisper.cpp/models/ggml-small.bin"
WORK="$HOME/yt_retr_tmp"

# Activer le venv Python qui contient yt-dlp + ajouter Deno au PATH
# (yt-dlp utilise Deno comme JS runtime pour parser les players YouTube — sans
# lui un warning s'affiche et certains formats deviennent indisponibles).
if [ -f "$HOME/wh/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$HOME/wh/bin/activate"
fi
export PATH="$HOME/.deno/bin:$HOME/wh/bin:$PATH"

mkdir -p "$TRANS_DIR" "$WORK"

echo "== Récupération dispatch =="
curl -fsSL -o "$WORK/list.json" "$MAIN_FILESERVER/tools/dispatch/retranscribe_yt.json"
N=$(python3 -c "import json;print(len(json.load(open('$WORK/list.json'))))")
echo "   $N épisodes à traiter"

for i in $(seq 0 $((N-1))); do
  GUID=$(python3 -c "import json;d=json.load(open('$WORK/list.json'));print(d[$i]['guid'])")
  URL=$(python3 -c "import json;d=json.load(open('$WORK/list.json'));print(d[$i]['youtubeUrl'])")
  TITLE=$(python3 -c "import json;d=json.load(open('$WORK/list.json'));print(d[$i]['title'][:50])")
  OUT="$TRANS_DIR/$GUID.txt"

  echo ""
  echo "=== [$((i+1))/$N] $TITLE ($GUID) ==="
  echo "    URL: $URL"

  # Skip si le transcript existe déjà ET a une taille raisonnable (>20K = vrai
  # contenu, pas un extrait court). On considère que c'est notre transcript YT
  # fraîchement produit.
  if [ -s "$OUT" ] && [ "$(stat -c%s "$OUT")" -gt 20480 ]; then
    echo "   ✓ déjà transcrit ($(du -h $OUT | cut -f1)), skip"
    continue
  fi

  echo "-- 1/4 yt-dlp audio --"
  rm -f "$WORK/cur.mp3" "$WORK/cur.wav" "$WORK/cur.json"
  # --remote-components ejs:github active le solver JS challenge complet (en plus
  # de Deno installé localement) → tous les formats audio dispos + plus rapide
  # qu'avant pour les vidéos avec challenge.
  if ! yt-dlp -q -x --audio-format mp3 \
        --remote-components ejs:github \
        -o "$WORK/cur.mp3" "$URL" </dev/null; then
    echo "   ✗ yt-dlp échec, skip"
    continue
  fi
  echo "   OK ($(du -h $WORK/cur.mp3 | cut -f1))"

  echo "-- 2/4 ffmpeg wav 16k mono --"
  ffmpeg -nostdin -y -loglevel error -i "$WORK/cur.mp3" -ar 16000 -ac 1 "$WORK/cur.wav" </dev/null

  echo "-- 3/4 whisper-cli (GPU) --"
  "$WHISPER_BIN" -m "$MODEL" -l fr -oj -of "$WORK/cur" "$WORK/cur.wav" </dev/null

  echo "-- 4/4 JSON -> txt --"
  GUID="$GUID" OUT="$OUT" WORK="$WORK" python3 - <<'PY'
import json, os
guid = os.environ["GUID"]; out = os.environ["OUT"]; work = os.environ["WORK"]
data = json.load(open(f"{work}/cur.json", encoding="utf-8", errors="replace"))
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
ls -lh "$TRANS_DIR" | tail -n 25
