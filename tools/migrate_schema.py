"""
migrate_schema.py — CLI pour migrations versionnées de `schemaVersion`.

Usage :

    python tools/migrate_schema.py --entity item --to-version 2 \\
        --source un-bon-moment --dry-run
    python tools/migrate_schema.py --entity item --to-version 2 \\
        --source un-bon-moment --apply

Défaut = `--dry-run` (aucune écriture). `--apply` explicite pour écrire.
Acquiert le verrou pipeline (refuse si `review_server` tourne, sauf
`--ignore-server-lock`).

Sortie : JSON sur stdout (parsing CI facilité).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import review_lock
from migrations import (
    MigrationRunner,
    UnknownEntityError,
    UnsupportedTargetVersionError,
)
from migrations.registry import get_known_entities
# SSOT du regex source_id : on importe depuis le repository plutôt que de
# dupliquer ici (`repository._base._SOURCE_ID_PATTERN`). Toute évolution du
# format slug est ainsi automatiquement propagée au CLI.
from repository._base import _SOURCE_ID_PATTERN as _RE_SOURCE_ID

# Chemins par défaut — overridable côté tests via monkeypatch.
ITEMS_BASE_DIR = Path("src/content/items")
MENTIONS_BASE_DIR = Path("src/content/mentions")
SOURCES_BASE_DIR = Path("src/content/sources")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Migre les fichiers JSON d'une entité (item/mention/source) "
            "vers une version cible de `schemaVersion`. Défaut = dry-run."
        )
    )
    # `choices` calculé dynamiquement depuis le registry (SSOT) — ajouter une
    # entité dans `KNOWN_ENTITIES` la rend automatiquement disponible côté CLI.
    p.add_argument("--entity", required=True, choices=get_known_entities())
    p.add_argument("--to-version", type=int, required=True)
    p.add_argument("--source", required=True, help="Slug de la source.")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true",
        help="N'écrit rien (défaut). Exclusif avec --apply.",
    )
    mode.add_argument(
        "--apply", action="store_true",
        help="Écrit les fichiers migrés sur disque.",
    )
    p.add_argument(
        "--ignore-server-lock", action="store_true",
        help="Force l'exécution même si review_server tourne.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    # Anti path-traversal sur le source_id (avant d'ouvrir le moindre fichier).
    if not _RE_SOURCE_ID.match(args.source):
        sys.stderr.write(
            f"source invalide: {args.source!r}. "
            f"Attendu: slug ^[a-z0-9]+(-[a-z0-9]+)*$.\n"
        )
        return 2
    dry_run = not args.apply
    try:
        with review_lock.acquire_pipeline_lock(force=args.ignore_server_lock):
            runner = MigrationRunner(
                items_base_dir=ITEMS_BASE_DIR,
                mentions_base_dir=MENTIONS_BASE_DIR,
                sources_base_dir=SOURCES_BASE_DIR,
            )
            stats = runner.run(
                entity=args.entity,
                source_id=args.source,
                target_version=args.to_version,
                dry_run=dry_run,
            )
    except (UnknownEntityError, UnsupportedTargetVersionError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 3
    except (review_lock.PipelineLockBusy, review_lock.ServerLockBusy) as exc:
        sys.stderr.write(f"{exc}\n")
        return 4
    sys.stdout.write(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
