"""migrate_guests_parsed.py — Peuple `ep.guestsParsed` (snapshot du parsing).

Pour chaque épisode JSON :
  - si `guestsParsed` est absent ou vide, calcule `_parse_guests(title, hosts)`
    et l'écrit dans le fichier.
  - n'altère JAMAIS `ep.guests` ni `recommendedBy` (données sacrées).
  - idempotent : un 2e run sur un fichier déjà migré ne touche à rien.

Usage :
    python tools/migrate_guests_parsed.py            # dry-run
    python tools/migrate_guests_parsed.py --apply    # écrit les fichiers
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Local imports (script lancé depuis la racine du projet)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (  # noqa: E402
    EPISODES_DIR, load_source, log, read_json, write_json_if_changed,
)
from review_lock import ServerLockBusy, acquire_pipeline_lock  # noqa: E402
from review_render_common import _parse_guests  # noqa: E402


def iter_episode_paths() -> list[tuple[str, Path]]:
    """Tous les épisodes : tuples (source_id, path). Tri stable pour reproductibilité."""
    out: list[tuple[str, Path]] = []
    if not EPISODES_DIR.exists():
        return out
    for src_dir in sorted(p for p in EPISODES_DIR.iterdir() if p.is_dir()):
        source_id = src_dir.name
        for p in sorted(src_dir.glob("*.json")):
            out.append((source_id, p))
    return out


def migrate(apply: bool = False) -> tuple[int, int, int]:
    """Retourne (n_total, n_skipped, n_changed)."""
    total = skipped = changed = 0
    hosts_by_source: dict[str, list[str]] = {}
    for source_id, ep_path in iter_episode_paths():
        total += 1
        ep = read_json(ep_path)
        # `in` plutôt que truthiness : un `[]` matérialisé compte comme
        # « déjà migré » et doit être skipped pour rester idempotent.
        if "guestsParsed" in ep:
            skipped += 1
            continue
        if source_id not in hosts_by_source:
            try:
                src = load_source(source_id)
                hosts_by_source[source_id] = list(src.get("hosts") or [])
            except FileNotFoundError:
                hosts_by_source[source_id] = []
        hosts = hosts_by_source[source_id]
        parsed = _parse_guests(ep.get("title", ""), hosts)
        if not parsed:
            # Rien à inférer : on écrit quand même `[]` pour matérialiser
            # « déjà tenté, rien trouvé » et éviter le fallback hot-path.
            ep["guestsParsed"] = []
        else:
            ep["guestsParsed"] = parsed
        if apply:
            if write_json_if_changed(ep_path, ep):
                changed += 1
                log.info("Migré %s : guestsParsed=%s",
                         ep_path.name, parsed)
        else:
            changed += 1
            print(f"[dry-run] {ep_path.relative_to(EPISODES_DIR)} → "
                  f"guestsParsed = {parsed}")
    return total, skipped, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="écrit les fichiers (sinon : dry-run)")
    parser.add_argument("--ignore-server-lock", action="store_true",
                        help="Ignore le verrou review_server (utile en dry-run).")
    args = parser.parse_args()

    # Coordination avec review_server : seulement nécessaire si --apply (la
    # dry-run ne touche pas le disque), mais on prend le verrou dans les
    # deux cas pour rester simple — le coût est nul si le serveur est down.
    try:
        lock_ctx = acquire_pipeline_lock(force=args.ignore_server_lock)
        lock_ctx.__enter__()
    except ServerLockBusy as exc:
        log.error("%s", exc)
        return 1
    try:
        total, skipped, changed = migrate(apply=args.apply)
        mode = "APPLIED" if args.apply else "DRY-RUN"
        print(f"\n[{mode}] total={total} skipped={skipped} changed={changed}")
        return 0
    finally:
        try:
            lock_ctx.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
