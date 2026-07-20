"""audit_core.types — Severity unifié, Suspicion base, Check Protocol.

Module SSOT pour les types fondamentaux partagés entre les 3 modules d'audit :
``lint``, ``match_audit``, ``enrich_audit``. Aucun de ces modules n'a besoin
de redéfinir ``Severity`` — il importe celui-ci.

Décisions architecturales (cf. ADR 0019) :

- **Severity (4 niveaux)** : ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``.
  StrEnum → sérialisation JSON value-compatible (``"info"``, ``"warning"``,
  ``"error"``, ``"critical"``). Les sidecars existants (qui n'utilisaient
  que 2-3 niveaux) restent valides à la lecture.

- **Suspicion (base)** : VO minimal (``kind``, ``detail``, ``severity``)
  utilisable par composition. Les VOs locaux (``LintIssue``,
  ``MatchSuspicion``, ``enrich_audit.Suspicion``) NE deviennent PAS
  des sous-classes — ils RESTENT distincts pour ne pas casser la sémantique
  module-spécifique. ``audit_core.Suspicion`` est offert pour les nouveaux
  audits (Spotify, MusicBrainz…) qui n'ont pas besoin de plus.

- **Check Protocol** : duck-typing structurel. Pas d'héritage requis.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class Severity(StrEnum):
    """Niveau de gravité d'un constat d'audit.

    Convention naturelle : élevé = grave.

    - ``INFO`` : observation sans impact (n'affecte pas l'exit code).
    - ``WARNING`` : à inspecter (exit code 2 si seul présent côté lint).
    - ``ERROR`` : doit être corrigé (exit code 1).
    - ``CRITICAL`` : mismatch quasi-certain (≥ ERROR). Sémantique
      module-spécifique : ``enrich_audit`` distingue WARNING (probable)
      de CRITICAL (quasi-certain).
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


_SEV_RANK: dict[str, int] = {
    Severity.INFO.value: 0,
    Severity.WARNING.value: 1,
    Severity.ERROR.value: 2,
    Severity.CRITICAL.value: 3,
}


def severity_rank(sev: Severity) -> int:
    """Rang numérique (0..3) — utile pour comparer / trier."""
    if not isinstance(sev, Severity):
        raise TypeError(
            f"severity_rank attend un Severity, pas {type(sev).__name__}"
        )
    return _SEV_RANK[sev.value]


def coerce_severity(value: Any) -> Severity:
    """Accepte ``Severity`` OU str — utile pour la lecture de sidecars
    legacy ou des payloads JSON externes.
    """
    if isinstance(value, Severity):
        return value
    if isinstance(value, str):
        try:
            return Severity(value)
        except ValueError as exc:
            raise ValueError(f"Severity inconnue : {value!r}") from exc
    raise TypeError(
        f"Severity attend str/Severity, pas {type(value).__name__}"
    )


def severity_value(sev: Severity | str) -> str:
    """Sérialise un ``Severity`` (ou une str legacy) en chaîne stable."""
    if isinstance(sev, Severity):
        return sev.value
    return str(sev)


@dataclass(frozen=True, slots=True)
class Suspicion:
    """VO minimal d'un constat d'audit.

    Les modules existants gardent leurs VOs locaux (sémantique métier
    spécifique). ``audit_core.Suspicion`` est utilisable par composition
    pour les nouveaux modules d'audit qui n'ont pas besoin de plus.

    Attributs :
        kind: identifiant stable du check (slug, ex. ``"title_mismatch"``).
        detail: message humain — pour reporter et debugger.
        severity: gravité (cf. :class:`Severity`). Par défaut WARNING.
    """

    kind: str
    detail: str
    severity: Severity = Severity.WARNING

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("Suspicion.kind doit être une str non vide")
        if not isinstance(self.detail, str):
            raise ValueError("Suspicion.detail doit être une str")
        if not isinstance(self.severity, Severity):
            raise ValueError(
                f"Suspicion.severity doit être Severity, "
                f"reçu {type(self.severity).__name__}"
            )


@runtime_checkable
class Check(Protocol):
    """Contrat structurel d'un check d'audit.

    Un check expose :
      - ``name`` : identifiant lisible (slug snake_case).
      - ``kind`` : ``Suspicion.kind`` émis (1 check ⇔ 1 kind par convention).
      - ``description`` : phrase courte — utile pour reporter & docs.

    Pas d'héritage requis : duck-typing structurel. Les checks concrets
    peuvent être des fonctions décorées ou des classes ; tant qu'ils
    exposent ces attributs et un ``__call__``, ils satisfont le protocole.
    """

    name: str
    kind: str
    description: str

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...  # pragma: no cover


# Type alias pratique : un check est une callable structurelle.
CheckCallable = Callable[..., Any]


__all__ = [
    "Check",
    "CheckCallable",
    "Severity",
    "Suspicion",
    "coerce_severity",
    "severity_rank",
    "severity_value",
]
