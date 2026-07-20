"""audit_core.cli_runner — primitives partagées pour les CLI d'audit.

Avant : 3 ``RunOptions`` divergents + 3 helpers ``_utcnow_iso`` dupliqués.
Après : un dataclass générique ``RunOptionsBase[Ctx, Report]`` + helpers
horloge / lockfile factorisés.

Les modules conservent leur ``RunOptions`` concret (la sémantique
``items``/``provider``/``transcript_repo`` est trop module-spécifique
pour être abstraite ici) mais peuvent hériter par composition.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Generic, Literal, TypeVar

Ctx = TypeVar("Ctx")
Report = TypeVar("Report")

OutputFormat = Literal["markdown", "json", "human", "none"]
Mode = Literal["check", "apply"]


def utcnow_iso() -> str:
    """ISO-8601 UTC, suffixe ``Z``, microsecondes tronquées.

    Helper centralisé pour ne plus dupliquer ``datetime.now(timezone.utc)``
    dans chaque cli_runner.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z",
    )


@dataclass(frozen=True, slots=True)
class RunOptionsBase(Generic[Ctx, Report]):
    """Base générique d'un RunOptions module-agnostic.

    Les modules sous-classent (ou composent) pour ajouter leurs champs
    spécifiques (``items``, ``provider``, ``transcript_repo``, etc.).

    Attributs partagés :
        source_id: slug source à auditer.
        mode: ``"check"`` (dry-run) ou ``"apply"``.
        output_format: format du rapport rendu.
        audited_at: ISO-8601 UTC injecté pour idempotence des sidecars.
            ``None`` → ``utcnow_iso()`` au moment de l'écriture.
        fail_on_suspect: si ``True`` et ≥ 1 suspect → exit code 1.
    """

    source_id: str
    mode: Mode = "check"
    output_format: OutputFormat = "human"
    audited_at: str | None = None
    fail_on_suspect: bool = False


__all__ = [
    "Ctx",
    "Mode",
    "OutputFormat",
    "Report",
    "RunOptionsBase",
    "utcnow_iso",
]
