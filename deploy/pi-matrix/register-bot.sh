#!/usr/bin/env bash
# Crée le compte bot et affiche son access_token (à mettre en secret GitHub).
# Utilise l'API register (UIA : session -> registration_token -> dummy).
#
# Prérequis : `.env` rempli, `jq` installé, Conduit démarré.
# Par défaut on tape le homeserver en local (127.0.0.1:6167) — pas besoin que
# le TLS/DNS soit prêt. Passe une autre URL en argument si besoin.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a

HS="${1:-http://127.0.0.1:6167}"
: "${BOT_USER:?BOT_USER manquant dans .env}"
: "${BOT_PASS:?BOT_PASS manquant dans .env}"
: "${MATRIX_REGISTRATION_TOKEN:?MATRIX_REGISTRATION_TOKEN manquant dans .env}"

reg() { curl -sS -X POST "$HS/_matrix/client/v3/register" \
  -H 'Content-Type: application/json' -d "$1"; }

# 1) Premier appel : récupère la `session` UIA.
r1=$(reg "{\"username\":\"$BOT_USER\",\"password\":\"$BOT_PASS\"}")
session=$(echo "$r1" | jq -r '.session // empty')
[ -n "$session" ] || { echo "Pas de session UIA. Réponse :"; echo "$r1" | jq .; exit 1; }

# 2) Soumet le registration_token.
r2=$(reg "{\"username\":\"$BOT_USER\",\"password\":\"$BOT_PASS\",\"auth\":{\"type\":\"m.login.registration_token\",\"token\":\"$MATRIX_REGISTRATION_TOKEN\",\"session\":\"$session\"}}")
token=$(echo "$r2" | jq -r '.access_token // empty')
uid=$(echo "$r2" | jq -r '.user_id // empty')

# 3) Certains serveurs exigent en plus une étape `m.login.dummy`.
if [ -z "$token" ]; then
  session=$(echo "$r2" | jq -r '.session // empty')
  r3=$(reg "{\"username\":\"$BOT_USER\",\"password\":\"$BOT_PASS\",\"auth\":{\"type\":\"m.login.dummy\",\"session\":\"$session\"}}")
  token=$(echo "$r3" | jq -r '.access_token // empty')
  uid=$(echo "$r3" | jq -r '.user_id // empty')
  [ -n "$token" ] || { echo "Échec register. Réponse :"; echo "$r3" | jq .; exit 1; }
fi

echo "=================================================================="
echo " Bot créé : $uid"
echo
echo " Secrets GitHub (Settings -> Secrets and variables -> Actions) :"
echo "   RECO_MATRIX_HOMESERVER = https://$MATRIX_DOMAIN"
echo "   RECO_MATRIX_TOKEN      = $token"
echo "   (RECO_MATRIX_ROOM viendra de create-room.sh)"
echo "=================================================================="
