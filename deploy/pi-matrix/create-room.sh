#!/usr/bin/env bash
# Crée le salon de notifs, t'y invite (MY_USER_ID) et affiche le room_id.
# Prérequis : `.env` rempli (bot déjà créé via register-bot.sh), `jq` installé.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a

HS="${1:-http://127.0.0.1:6167}"
: "${BOT_USER:?}"; : "${BOT_PASS:?}"; : "${MY_USER_ID:?MY_USER_ID manquant dans .env}"

# Login du bot -> access_token.
tok=$(curl -sS -X POST "$HS/_matrix/client/v3/login" -H 'Content-Type: application/json' \
  -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"$BOT_USER\"},\"password\":\"$BOT_PASS\"}" \
  | jq -r '.access_token // empty')
[ -n "$tok" ] || { echo "Login bot échoué (BOT_USER/BOT_PASS ?)."; exit 1; }

# Crée un salon privé et invite ton compte.
room=$(curl -sS -X POST "$HS/_matrix/client/v3/createRoom" \
  -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
  -d "{\"name\":\"Reco — notifications\",\"topic\":\"Épisodes & signalements\",\"preset\":\"private_chat\",\"invite\":[\"$MY_USER_ID\"]}" \
  | jq -r '.room_id // empty')
[ -n "$room" ] || { echo "Création du salon échouée."; exit 1; }

echo "=================================================================="
echo " Salon créé : $room"
echo " -> Accepte l'invitation dans Element (compte $MY_USER_ID)."
echo
echo " Secret GitHub :"
echo "   RECO_MATRIX_ROOM = $room"
echo "=================================================================="
