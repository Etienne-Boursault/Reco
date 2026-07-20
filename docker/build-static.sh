#!/usr/bin/env sh
# Helper hors-conteneur : rebuild le site Astro localement (avant `docker compose up`).
# Utile si on a édité du code Astro et qu'on veut servir dist/ via reco-site
# sans reconstruire toute l'image.
set -eu
cd "$(dirname "$0")/.."
echo "==> npm ci"
npm ci --include=dev
echo "==> astro build"
npm run build
echo "==> dist/ prêt."
