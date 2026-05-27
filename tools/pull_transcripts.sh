#!/usr/bin/env bash
# pull_transcripts.sh — Rapatrie les transcriptions produites par le portable.
#
# Le worker GPU sur le portable expose ~/transcripts/un-bon-moment/ sur :8002.
# Ce script télécharge tout ce qui manque dans le dossier projet.
#
# Usage : bash tools/pull_transcripts.sh [http://<laptop_ip>:8002]
set -e

LAPTOP_URL="${1:-http://192.168.1.219:8002}"
DEST="tools/output/transcripts/un-bon-moment"
mkdir -p "$DEST"

# Récupère la liste des .txt depuis le listing HTTP de python -m http.server.
LIST=$(curl -s "$LAPTOP_URL/" | grep -oE 'href="[^"]+\.txt"' | sed -E 's/href="(.*)"/\1/' | sort -u) || true
[ -z "$LIST" ] && { echo "Aucun fichier .txt trouvé sur $LAPTOP_URL — le worker tourne-t-il ?"; exit 0; }

new=0
for f in $LIST; do
  TO="$DEST/$f"
  if [ ! -f "$TO" ]; then
    if curl -s -f -o "$TO" "$LAPTOP_URL/$f"; then
      echo "✓ $f"
      new=$((new+1))
    fi
  fi
done
echo "Rapatriement terminé : $new nouveau(x) fichier(s)."
