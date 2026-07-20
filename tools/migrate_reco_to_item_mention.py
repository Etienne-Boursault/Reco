"""
migrate_reco_to_item_mention.py — CLI pour la migration recos → Items+Mentions.

Usage :

    python tools/migrate_reco_to_item_mention.py --source un-bon-moment --dry-run
    python tools/migrate_reco_to_item_mention.py --source un-bon-moment --apply
    python tools/migrate_reco_to_item_mention.py --source un-bon-moment --verify

Acquiert le verrou pipeline (`review_lock.acquire_pipeline_lock`) : refuse
si le `review_server` tourne, sauf `--ignore-server-lock`.

Le défaut est `--dry-run` (aucune écriture). Pour appliquer, passer
`--apply` explicitement.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

import review_lock
from repository.item_repo import ItemRepoJson
from repository.mention_repo import MentionRepoJson
from repository.migration import MigrationService

# Constantes de chemin — overridable côté tests via monkeypatch
# (legacy : compat avec les tests historiques) OU via les arguments CLI
# `--recos-dir/--items-dir/--mentions-dir` (B12, plus propre).
RECOS_BASE_DIR = Path("src/content/recos")
ITEMS_BASE_DIR = Path("src/content/items")
MENTIONS_BASE_DIR = Path("src/content/mentions")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Migre les recos legacy d'une source vers Items+Mentions. "
            "Modes mutuellement exclusifs : --dry-run | --apply | --verify. "
            "Défaut : dry-run (aucune écriture)."
        )
    )
    p.add_argument("--source", required=True, help="Slug de la source (ex. un-bon-moment).")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true",
        help="N'écrit rien, affiche les stats (défaut). Exclusif avec --apply/--verify.",
    )
    mode.add_argument(
        "--apply", action="store_true",
        help="Écrit Items+Mentions sur disque. Exclusif avec --dry-run/--verify.",
    )
    mode.add_argument(
        "--verify", action="store_true",
        help="Vérifie la cohérence post-migration (pas d'écriture). "
             "Exclusif avec --dry-run/--apply.",
    )
    p.add_argument(
        "--ignore-server-lock", action="store_true",
        help="Force l'exécution même si review_server tourne (dangereux).",
    )
    # B12 : chemins overridables via args (plus propre que monkeypatch).
    p.add_argument(
        "--recos-dir", type=Path, default=None,
        help=f"Racine des recos legacy (défaut: {RECOS_BASE_DIR}).",
    )
    p.add_argument(
        "--items-dir", type=Path, default=None,
        help=f"Racine de sortie des Items (défaut: {ITEMS_BASE_DIR}).",
    )
    p.add_argument(
        "--mentions-dir", type=Path, default=None,
        help=f"Racine de sortie des Mentions (défaut: {MENTIONS_BASE_DIR}).",
    )
    return p


def _select_mode(args: argparse.Namespace) -> str:
    if args.verify:
        return "verify"
    if args.apply:
        return "apply"
    return "dry-run"


def _log_header(mode: str, source: str, recos_dir: Path) -> None:
    """D8 : log structuré sur stderr (ne casse pas le parsing stdout JSON)."""
    ts = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    print(
        f"[migrate_reco_to_item_mention] mode={mode} source={source} "
        f"recos_dir={recos_dir} timestamp={ts}",
        file=sys.stderr,
    )


def _run(args: argparse.Namespace) -> int:
    """Exécute la commande sélectionnée. Retourne un exit code."""
    # Args > module constants > defaults. Les constants restent
    # monkeypatchables pour les tests historiques.
    recos_dir = args.recos_dir if args.recos_dir is not None else RECOS_BASE_DIR
    items_dir = args.items_dir if args.items_dir is not None else ITEMS_BASE_DIR
    mentions_dir = (
        args.mentions_dir if args.mentions_dir is not None else MENTIONS_BASE_DIR
    )

    mode = _select_mode(args)
    _log_header(mode, args.source, recos_dir)

    item_repo = ItemRepoJson(items_dir, args.source)
    mention_repo = MentionRepoJson(mentions_dir, args.source)
    service = MigrationService(
        item_repo=item_repo,
        mention_repo=mention_repo,
        sources_dir=recos_dir,
        source_id=args.source,
    )

    if mode == "verify":
        stats = service.verify()
        print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))
        return 0 if stats.n_errors == 0 else 2

    dry_run = mode == "dry-run"
    stats = service.migrate(dry_run=dry_run)
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))
    return 0 if stats.n_errors == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        with review_lock.acquire_pipeline_lock(force=args.ignore_server_lock):
            return _run(args)
    except review_lock.LockBusy as e:
        print(f"ERREUR verrou: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
