"""
migrate_types.py — Migration de schéma : `type` (string) → `types` (list[string]).

Parcourt tous les fichiers `src/content/recos/<source>/*.json` et :
  - si la reco a un champ `type` (string), ajoute `types: [type]` et supprime `type` ;
  - si la reco a déjà `types`, ne touche pas (idempotent) ;
  - si la reco n'a ni `type` ni `types`, laisse inchangé.

Usage :
    python migrate_types.py                  # toutes les sources
    python migrate_types.py --source un-bon-moment
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import RECOS_DIR, log, read_json, write_json_if_changed
from review_lock import ServerLockBusy, acquire_pipeline_lock


def migrate_reco(data: dict[str, Any]) -> dict[str, Any] | None:
    """Renvoie une nouvelle reco migrée si une migration est nécessaire, sinon None.

    Règles :
      - Si `types` est présent (liste non vide), aucune migration : renvoie None.
      - Si `type` est présent et `types` absent, renvoie un dict sans `type` mais
        avec `types: [type]`.
      - Sinon (ni `type` ni `types`), renvoie None.
    """
    if isinstance(data.get("types"), list) and data["types"]:
        return None
    rtype = data.get("type")
    if not isinstance(rtype, str) or not rtype:
        return None
    new_data = {k: v for k, v in data.items() if k != "type"}
    new_data["types"] = [rtype]
    return new_data


def migrate_file(path: Path) -> bool:
    """Migre un fichier JSON sur disque. Renvoie True si modifié."""
    try:
        data = read_json(path)
    except (OSError, ValueError) as exc:
        log.warning("  Ignoré (lecture impossible) %s : %s", path.name, exc)
        return False
    migrated = migrate_reco(data)
    if migrated is None:
        return False
    return write_json_if_changed(path, migrated)


def migrate_source(source_id: str) -> int:
    """Migre toutes les recos d'une source donnée. Renvoie le nombre de fichiers migrés."""
    src_dir = RECOS_DIR / source_id
    if not src_dir.is_dir():
        log.warning("Source inconnue : %s (dossier %s absent).", source_id, src_dir)
        return 0
    count = 0
    for path in sorted(src_dir.glob("*.json")):
        if migrate_file(path):
            count += 1
    log.info("Source %s : %d fichier(s) migré(s).", source_id, count)
    return count


def migrate_all() -> int:
    """Migre toutes les sources présentes dans `RECOS_DIR`. Renvoie le total."""
    if not RECOS_DIR.is_dir():
        log.warning("Dossier recos absent : %s", RECOS_DIR)
        return 0
    total = 0
    for sub in sorted(RECOS_DIR.iterdir()):
        if sub.is_dir():
            total += migrate_source(sub.name)
    log.info("Total : %d fichier(s) migré(s).", total)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migre les recos JSON du champ `type` (string) vers `types` (list)."
    )
    parser.add_argument("--source", default=None,
                        help="ID de source à migrer (sinon : toutes).")
    parser.add_argument("--ignore-server-lock", action="store_true",
                        help="Ignore le verrou review_server.")
    args = parser.parse_args()

    import sys as _sys  # noqa: PLC0415
    try:
        lock_ctx = acquire_pipeline_lock(force=args.ignore_server_lock)
        lock_ctx.__enter__()
    except ServerLockBusy as exc:
        log.error("%s", exc)
        _sys.exit(1)
    try:
        if args.source:
            migrate_source(args.source)
        else:
            migrate_all()
    finally:
        try:
            lock_ctx.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
