#!/usr/bin/env sh
# Reco — entrypoint conteneur.
# Routes : review (défaut) | serve | pipeline | build | shell | <cmd...>
set -eu

SOURCE_DEFAULT="${RECO_SOURCE:-un-bon-moment}"

cmd="${1:-review}"
shift || true

case "$cmd" in
  review)
    # review_server bind 127.0.0.1 par défaut → on lance via launcher qui
    # monkeypatche HTTPServer pour écouter 0.0.0.0 (sinon inaccessible
    # depuis l'extérieur du conteneur). Cf. docker/review_launcher.py.
    exec python /app/docker/review_launcher.py --source "$SOURCE_DEFAULT" --port 8000
    ;;
  serve)
    # Mini serveur HTTP statique pour /app/dist (site Astro builé).
    exec python -m http.server 4321 --directory /app/dist --bind 0.0.0.0
    ;;
  pipeline)
    SOURCE="${1:-$SOURCE_DEFAULT}"
    echo "==> [pipeline] source=$SOURCE"
    echo "--> build_cache"
    python /app/tools/build_cache.py --source "$SOURCE"
    echo "--> lint_dataset (warnings tolérés)"
    python -m lint_dataset --source "$SOURCE" || true
    echo "--> audit_yt_acast"
    python /app/tools/audit_yt_acast.py --source "$SOURCE" --check --format json || true
    echo "--> audit_tmdb"
    python /app/tools/audit_tmdb.py --source "$SOURCE" --report markdown || true
    echo "==> [pipeline] done."
    ;;
  build)
    # Rebuild statique nécessite Node — pas présent dans runtime slim.
    echo "ERR: 'build' n'est pas dispo dans l'image runtime (Node absent)." >&2
    echo "     Reconstruire l'image : docker compose build" >&2
    exit 2
    ;;
  shell|sh)
    exec /bin/sh
    ;;
  *)
    # Passe-plat — lance n'importe quelle commande dans l'env du venv.
    exec "$cmd" "$@"
    ;;
esac
