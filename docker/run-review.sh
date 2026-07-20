#!/usr/bin/env sh
# Helper hors-conteneur : raccourci `docker compose up reco-review`.
set -eu
cd "$(dirname "$0")/.."
exec docker compose up -d reco-review
