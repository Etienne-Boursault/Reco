"""audit_core.trail — JsonlAuditTrail / NoopAuditTrail factorisés.

Pattern copié de ``tools/match_audit/audit_trail.py`` (déjà mûr) et offert
en SSOT pour les modules futurs.

Le ``JsonlAuditTrail`` est append-only : une ligne JSON par événement,
``mkdir parents=True`` à la première écriture, pas de rotation
(un fichier par ``--apply``).
"""
from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuditTrail(Protocol):
    """Contrat structurel d'un journal d'audit (DIP)."""

    def record(self, event: Mapping[str, Any]) -> None: ...  # pragma: no cover


class NoopAuditTrail:
    """Implémentation no-op — utile pour les modes ``--check`` (dry-run)."""

    def record(self, event: Mapping[str, Any]) -> None:  # noqa: D401, ARG002
        return None


class JsonlAuditTrail:
    """Écrit chaque événement comme une ligne JSON dans ``path``.

    Append-only. Pas de rotation. Le fichier est créé à la première
    écriture (parents inclus).
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
        """Itère les événements (pour ``--undo-last`` ou audit forensic)."""
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


__all__ = ["AuditTrail", "JsonlAuditTrail", "NoopAuditTrail"]
