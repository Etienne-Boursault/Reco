"""audit_tmdb.py — CLI : audit post-enrichissement TMDB.

Pour une source donnée, lit tous ses Items, récupère pour chacun les
données TMDB depuis un cache local (``tools/output/tmdb_cache/<id>.json``),
exécute les checks de `tools.enrich_audit` et produit un rapport.

Mode par défaut : **dry-run** (n'écrit rien — calculé via ``not args.apply``,
cf. CR senior C1).

Mode ``--apply`` : écrit les verdicts en sidecars
``tools/output/enrich_audit/<source>/<item_id>.json``.

Mode ``--undo-last`` : restaure le dernier snapshot archivé d'une source
(CR archi P1 #16).

Codes de sortie (CR senior M9) :
  - 0 : OK, pas de suspect.
  - 1 : erreur fatale (lock busy, source introuvable, etc.).
  - 2 : au moins un suspect détecté (utile en CI avec ``--fail-on-suspect``).

Usage :
    python tools/audit_tmdb.py --source un-bon-moment
    python tools/audit_tmdb.py --source un-bon-moment --apply
    python tools/audit_tmdb.py --source un-bon-moment --report json
    python tools/audit_tmdb.py --source un-bon-moment --apply --fail-on-suspect
    python tools/audit_tmdb.py --source un-bon-moment --undo-last

NB : ce CLI **n'appelle jamais l'API TMDB**. S'il n'y a pas de cache local
pour un tmdb_id donné, l'item est compté dans ``skipped_no_cache``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import CONTENT_DIR, OUTPUT_DIR, log
from enrich_audit.cli_runner import (
    RunOptions,
    default_service,
    format_json,
    format_markdown,
    make_cache_provider,
    run_audit,
)
from enrich_audit.flag_writer import restore_archive
from enrich_audit.thresholds import (
    DEFAULT_FILM_MIN_RUNTIME,
    DEFAULT_TITLE_THRESHOLD,
    DEFAULT_YEAR_TOLERANCE,
)
from repository.item_repo import ItemRepoJson
from review_lock import ServerLockBusy, acquire_pipeline_lock

_DEFAULT_TMDB_CACHE: Path = OUTPUT_DIR / "tmdb_cache"
_DEFAULT_ITEMS_DIR: Path = CONTENT_DIR / "items"
_DEFAULT_JSONL_LOG: Path = OUTPUT_DIR / "logs" / "audit_tmdb.jsonl"


# Exit codes — CR senior M9
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_SUSPECTS = 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audit_tmdb",
        description="Audit post-enrichissement TMDB (détecte les mauvais matches).",
    )
    p.add_argument("--source", required=True, help="ID de la source (slug podcast).")

    # CR senior C1 : `--apply` est la seule action écrivante. Le dry-run est
    # le défaut (calculé comme `not args.apply`).
    p.add_argument(
        "--apply",
        action="store_true",
        help="Écrit les sidecars dans tools/output/enrich_audit/.",
    )
    p.add_argument(
        "--undo-last",
        action="store_true",
        help=(
            "Restaure le dernier snapshot d'archive d'une source "
            "(annule le précédent --apply)."
        ),
    )
    p.add_argument(
        "--report",
        choices=("markdown", "json", "none"),
        default="markdown",
        help="Format du rapport stdout (default: markdown).",
    )
    p.add_argument(
        "--items-dir",
        type=Path,
        default=_DEFAULT_ITEMS_DIR,
        help=f"Racine des items JSON (default: {_DEFAULT_ITEMS_DIR}).",
    )
    p.add_argument(
        "--tmdb-cache-dir",
        type=Path,
        default=_DEFAULT_TMDB_CACHE,
        help=f"Cache local TMDB (default: {_DEFAULT_TMDB_CACHE}).",
    )
    p.add_argument(
        "--sidecar-dir",
        type=Path,
        default=None,
        help="Override du dossier sidecar (default: tools/output/enrich_audit/).",
    )
    p.add_argument(
        "--jsonl-log",
        type=Path,
        default=_DEFAULT_JSONL_LOG,
        help=f"Log JSONL des suspects (default: {_DEFAULT_JSONL_LOG}).",
    )
    p.add_argument(
        "--no-jsonl-log",
        action="store_true",
        help="Désactive le log JSONL.",
    )
    p.add_argument(
        "--ignore-server-lock",
        action="store_true",
        help="Forcer le lock même si review_server tourne.",
    )
    p.add_argument(
        "--fail-on-suspect",
        action="store_true",
        help="Exit code 2 si au moins un suspect (default: 0).",
    )
    # CR senior H4 : seuils injectables CLI.
    p.add_argument(
        "--title-threshold",
        type=float,
        default=DEFAULT_TITLE_THRESHOLD,
        help=f"Seuil de similarité titre (default: {DEFAULT_TITLE_THRESHOLD}).",
    )
    p.add_argument(
        "--year-tolerance",
        type=int,
        default=DEFAULT_YEAR_TOLERANCE,
        help=f"Tolérance ± années (default: {DEFAULT_YEAR_TOLERANCE}).",
    )
    p.add_argument(
        "--film-min-runtime",
        type=int,
        default=DEFAULT_FILM_MIN_RUNTIME,
        help=f"Runtime min film en min (default: {DEFAULT_FILM_MIN_RUNTIME}).",
    )
    # Provider lock-free pour les tests / measures.
    p.add_argument(
        "--no-lru-cache",
        action="store_true",
        help="Désactive le cache LRU du provider TMDB (perf debug).",
    )
    return p


def run(args: argparse.Namespace) -> int:
    """Exécute un run avec un namespace déjà parsé (CR senior H5)."""
    if args.undo_last:
        n = restore_archive(args.source, base_dir=args.sidecar_dir)
        log.info(
            "undo-last source=%s : %d sidecar(s) restauré(s) depuis l'archive",
            args.source, n,
        )
        return EXIT_OK if n > 0 else EXIT_ERROR

    repo = ItemRepoJson(args.items_dir, args.source)
    items = tuple(repo.iter_all())
    if not items:
        log.warning("Aucun item trouvé pour la source %r dans %s",
                    args.source, args.items_dir)

    provider = make_cache_provider(
        args.tmdb_cache_dir, use_lru=not args.no_lru_cache,
    )

    service = default_service(
        title_threshold=args.title_threshold,
        year_tolerance=args.year_tolerance,
        film_min_runtime=args.film_min_runtime,
    )

    jsonl_path: Path | None = None
    if not args.no_jsonl_log:
        jsonl_path = args.jsonl_log

    opts = RunOptions(
        source_id=args.source,
        items=items,
        provider=provider,
        apply=bool(args.apply),
        sidecar_base_dir=args.sidecar_dir,
        service=service,
        jsonl_log_path=jsonl_path,
    )
    report = run_audit(opts)

    if args.report == "markdown":
        sys.stdout.write(format_markdown(report))
    elif args.report == "json":
        sys.stdout.write(format_json(report))
    # "none" → silence

    log.info(
        "Audit %s : %d audited / %d suspect / %d clean "
        "(skipped: %d no-tmdb, %d no-cache, %d check-errors)",
        args.source,
        report.audited_count,
        report.suspect_count,
        report.clean_count,
        report.skipped_no_tmdb,
        report.skipped_no_cache,
        report.skipped_check_error,
    )

    if args.fail_on_suspect and report.suspect_count > 0:
        return EXIT_SUSPECTS
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    # CR senior H5 : parse une seule fois.
    args = build_parser().parse_args(argv)
    try:
        with acquire_pipeline_lock(force=args.ignore_server_lock):
            return run(args)
    except ServerLockBusy as exc:
        log.error("%s", exc)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
