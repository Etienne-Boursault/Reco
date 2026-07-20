"""build_cache.py — CLI : (re)construit le cache SQLite depuis les JSON.

Usage :
    python tools/build_cache.py --source un-bon-moment
    python tools/build_cache.py --source all --force --vacuum --optimize

La logique métier vit dans ``cache.cli_runner`` (CR archi P2-5) ; ce
module se limite à l'argparse et au câblage du lock pipeline.

Exit codes :
    0 — OK
    1 — erreur d'exécution (lock pris, FTS5 absent, exception)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final, Sequence

# Le pyproject ajoute tools/ au pythonpath. Imports plats.
from cache.cli_runner import BuildCacheRunOptions, run_build_cache
from common import CONTENT_DIR, OUTPUT_DIR, log
from review_lock import ServerLockBusy, acquire_pipeline_lock

_DEFAULT_DB_PATH: Final[Path] = OUTPUT_DIR / "cache" / "reco.sqlite"
_ITEMS_DIR: Final[Path] = CONTENT_DIR / "items"
_MENTIONS_DIR: Final[Path] = CONTENT_DIR / "mentions"
_EPISODES_DIR: Final[Path] = CONTENT_DIR / "episodes"


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="build_cache",
        description="Construit le cache SQLite (FTS5) depuis les JSON `src/content/`.",
    )
    p.add_argument(
        "--source",
        default="all",
        help='ID de source (ex. "un-bon-moment") ou "all" pour toutes.',
    )
    p.add_argument(
        "--db",
        type=Path,
        default=_DEFAULT_DB_PATH,
        help=f"Chemin du fichier SQLite (défaut: {_DEFAULT_DB_PATH}).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Ignorer le verrou serveur (review_server) si tenu.",
    )
    p.add_argument(
        "--vacuum",
        action="store_true",
        help="Lancer VACUUM après le build (compaction, +durée).",
    )
    p.add_argument(
        "--optimize",
        action="store_true",
        help="Lancer FTS5 'optimize' (compaction de l'index, +durée).",
    )
    p.add_argument(
        "--allow-unsafe-db-path",
        action="store_true",
        help="(dev uniquement) Désactive la vérification --db sous OUTPUT_DIR.",
    )
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    source_id = None if args.source == "all" else args.source
    allowed_root = None if args.allow_unsafe_db_path else OUTPUT_DIR

    try:
        opts = BuildCacheRunOptions(
            source_id=source_id,
            db_path=args.db,
            items_dir=_ITEMS_DIR,
            mentions_dir=_MENTIONS_DIR,
            episodes_dir=_EPISODES_DIR,
            force=args.force,
            vacuum=args.vacuum,
            optimize=args.optimize,
            allowed_db_root=allowed_root,
        )
    except ValueError as exc:
        log.error("Paramètres invalides : %s", exc)
        return 1

    try:
        rc, _stats = run_build_cache(
            opts,
            lock_factory=acquire_pipeline_lock,
            log=log.info,
        )
    except ServerLockBusy as e:
        log.error("review_server tient le verrou : %s", e)
        return 1
    except Exception as e:  # pragma: no cover (catch-all CLI)
        log.exception("Build cache a échoué : %s", e)
        return 1
    return rc


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
