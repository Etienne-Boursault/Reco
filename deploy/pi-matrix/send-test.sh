#!/usr/bin/env bash
# Envoie un message de test dans le salon, pour valider la chaîne bout-en-bout.
# Usage : ./send-test.sh '!roomid:matrix.exemple.fr'   (ou RECO_MATRIX_ROOM en env)
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a

HS="${HS:-http://127.0.0.1:6167}"
ROOM="${1:-${RECO_MATRIX_ROOM:?Passe le room_id en argument ou via RECO_MATRIX_ROOM}}"
: "${BOT_USER:?}"; : "${BOT_PASS:?}"

tok=$(curl -sS -X POST "$HS/_matrix/client/v3/login" -H 'Content-Type: application/json' \
  -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"$BOT_USER\"},\"password\":\"$BOT_PASS\"}" \
  | jq -r '.access_token // empty')
[ -n "$tok" ] || { echo "Login bot échoué."; exit 1; }

room_enc=$(jq -rn --arg r "$ROOM" '$r|@uri')
txn=$(date +%s%N)
code=$(curl -sS -o /dev/null -w '%{http_code}' -X PUT \
  "$HS/_matrix/client/v3/rooms/$room_enc/send/m.room.message/$txn" \
  -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
  -d '{"msgtype":"m.notice","body":"✅ Test Reco : la chaîne de notifications fonctionne."}')
echo "PUT message -> HTTP $code (200 = OK, regarde Element)."
