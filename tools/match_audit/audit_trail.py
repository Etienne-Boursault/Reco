"""``AuditTrail`` — journal append-only des actions ``--apply``.

Permet :
- la traçabilité du run (qui/quand/quoi) — CR archi #11 + CR senior H6 ;
- l'``--undo-last`` (CR archi #6) en relisant la dernière entrée pour
  retrouver les sidecars à supprimer.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Mapping


class NoopAuditTrail:
    """Implémentation no-op — utile pour les modes ``--check`` (dry-run)."""

    def record(self, event: Mapping[str, Any]) -> None:  # noqa: D401
        return None


class JsonlAuditTrail:
    """Écrit chaque événement comme une ligne JSON dans ``path`` (append-only).

    Le fichier est créé à la première écriture (parents inclus). Aucune
    rotation n'est effectuée — un fichier par ``--apply`` est l'usage
    cible (voir ``cli_runner._trail_path_for_run``).
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def record(self, event: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(dict(event), ensure_ascii=False, sort_keys=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def iter_events(self) -> Iterator[dict[str, Any]]:
        """Itère les événements (pour ``--undo-last``)."""
        if not self._path.exists():
            return iter(())

        def _gen() -> Iterator[dict[str, Any]]:
            with self._path.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        continue
                    if isinstance(obj, dict):
                        yield obj

        return _gen()


__all__ = ["JsonlAuditTrail", "NoopAuditTrail"]
