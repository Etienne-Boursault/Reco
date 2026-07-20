#!/usr/bin/env bash
# pull_transcripts_compare.sh — Rapatrie les transcriptions de comparaison
# (medium / large-v3) depuis le laptop. Ne touche PAS aux transcripts small
# de production : sortie dans tools/output/whisper-cmp/<model>/<guid>.txt.
#
# Le worker_gpu_compare.sh sur le laptop sert ~/transcripts/ sur :8002.
# On y trouve deux sous-dossiers : un-bon-moment-medium/ et un-bon-moment-large-v3/.
#
# Usage : bash tools/pull_transcripts_compare.sh [http://<laptop_ip>:8002]
set -e

LAPTOP_URL="${1:-http://192.168.1.219:8002}"
SOURCE="un-bon-moment"

for MODEL in medium large-v3; do
  DEST="tools/output/whisper-cmp/$MODEL"
  SUB="$SOURCE-$MODEL"
  mkdir -p "$DEST"
  echo "== $MODEL : $LAPTOP_URL/$SUB/ → $DEST/ =="
  LIST=$(curl -s "$LAPTOP_URL/$SUB/" \
    | grep -oE 'href="[^"]+\.txt"' \
    | sed -E 's/href="(.*)"/\1/' \
    | sort -u) || true
  if [ -z "$LIST" ]; then
    echo "   (aucun fichier trouvé — worker_gpu_compare.sh tourne-t-il ?)"
    continue
  fi
  new=0
  for f in $LIST; do
    TO="$DEST/$f"
    if [ ! -f "$TO" ]; then
      if curl -s -f -o "$TO" "$LAPTOP_URL/$SUB/$f"; then
        echo "   ✓ $f"
        new=$((new+1))
      fi
    fi
  done
  echo "   $new nouveau(x) fichier(s)."
done

echo ""
echo "Étape suivante : lancer l'extraction comparative locale :"
echo "  python tools/extract_recos_compare.py --source un-bon-moment"
