"""review_server.py — Outil de relecture LOCAL (hors site public).

Point d'entrée du serveur de relecture. La logique a été splitée :
- `review_handler_base` : plomberie HTTP (sécurité, cache, réponses).
- `review_routes`        : handlers GET/POST métier (classe `Handler`).
- `review_render*`       : rendu HTML.

Single-threaded by design (HTTPServer, not ThreadingHTTPServer).
Outil local mono-utilisateur — pas de protection de concurrence intentionnelle.
Voir docs/yagni.md pour la justification.

Usage : ``python review_server.py --source un-bon-moment [--port 8000]``
"""

from __future__ import annotations

import argparse
import sys
from functools import partial
from http.server import HTTPServer

from dotenv import load_dotenv

from common import TOOLS_DIR, log, read_json  # noqa: F401 — read_json rétro-compat tests
from review_lock import PipelineLockBusy, ServerLockBusy, acquire_server_lock
from review_routes import (
    Handler,
    _allocate_new_reco,  # noqa: F401 — rétro-compat tests
    _cleanup_orphan_tmp_files,
)

# --- Ré-exports de compatibilité (tests historiques) -------------------------
# Les nouveaux callers doivent importer depuis les modules dédiés. On garde ces
# alias pour ne pas casser la suite tests/test_review_server.py existante.
from review_handler_base import (  # noqa: F401 — rétro-compat tests
    _MAX_POST_BYTES,
    _RE_GUID,
    _RE_RECO_ID,
    _RECO_PATH_CACHE,
    _SECURITY_HEADERS,
    _invalidate_reco_path_cache,
    _invalidates_reco_cache,
    _rebuild_reco_path_cache,
    _reco_path,
)
from review_render import (  # noqa: F401 — rétro-compat tests
    _CLIENT_JS,
    _CSS_PATH,
    _STOP,
    _context_around,
    _embed_url,
    _ep_header,
    _flash_banner,
    _fmt,
    _load_groups,
    _load_transcript,
    _parse_guests,
    _reco_card,
    _render_episode,
    _render_index,
    _shell,
    _style,
    _ts_seconds,
    _yt_id,
)
from review_render_cluster import (  # noqa: F401 — rétro-compat tests
    render_merge_preview,
    render_pick_canonical,
)

__all__ = ["Handler", "main"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Outil de relecture local des recos.")
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Charge tools/.env pour que TMDB_API_KEY / SPOTIFY_* soient disponibles
    # dans os.environ — le bouton « Ré-enrichir » en a besoin.
    load_dotenv(TOOLS_DIR / ".env")

    # #E — nettoie les .tmp orphelins éventuellement laissés par un crash.
    _cleanup_orphan_tmp_files(args.source)

    # Verrou de coordination : refuse de démarrer si un script pipeline
    # tourne (extract_recos, enrich_*, migrate_*) — sinon ils écraseraient
    # silencieusement nos validations manuelles. Le verrou est tenu pour
    # toute la durée du serveur (cf. tools/review_lock.py).
    try:
        ctx = acquire_server_lock()
        ctx.__enter__()
    except (PipelineLockBusy, ServerLockBusy) as exc:
        log.error("%s", exc)
        sys.exit(1)

    try:
        handler = partial(Handler, source_id=args.source)
        server = HTTPServer(("127.0.0.1", args.port), handler)
        # #23 sécu — le code suppose single-threaded (cf. docs/yagni.md, pas
        # de lock applicatif). Si quelqu'un swap pour `ThreadingHTTPServer`,
        # on veut casser explicitement plutôt qu'introduire des races
        # silencieuses (le filelock cross-process n'aide pas en intra-process).
        from http.server import ThreadingHTTPServer  # noqa: PLC0415
        assert not isinstance(server, ThreadingHTTPServer), (
            "review_server est single-threaded by design (pas de lock)"
        )
        log.info("Relecture sur http://localhost:%d  (Ctrl+C pour arrêter)",
                 args.port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            log.info("Arrêt.")
    finally:
        try:
            ctx.__exit__(None, None, None)
        except Exception:  # noqa: BLE001 — best-effort release
            pass


if __name__ == "__main__":
    main()
