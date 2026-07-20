"""Types valeur partagés (SRP — un module ≡ une responsabilité).

Note d'alignement (cf. ADR 0015) : ce module DUPLIQUE volontairement les
notions ``Suspicion``/``Severity`` qui vivent aussi dans
``tools.enrich_audit``. La convergence (extraction d'un module
``tools.audit_core``) est REPORTÉE à la fin de la Phase 1 (zone
``tools/enrich_audit/`` actuellement éditée par un autre agent).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from audit_core.types import Severity  # SSOT — cf. ADR 0019

# Note ADR 0019 : ``Severity`` est réexporté depuis ``audit_core``.
# match_audit n'utilise sémantiquement que ``ERROR``/``WARNING`` (un check
# WARNING ne pose pas le flag ``matchSuspect=true`` ; ERROR le pose),
# mais ``INFO`` et ``CRITICAL`` sont accessibles via le même enum
# (option B 4-niveaux unifiés — zéro casse de sérialisation).


# Famille connue de checks. On garde ``str`` libre (forward-compat : un
# fork peut ajouter ``kind="my_custom_check"`` sans recompiler — cf. CR
# archi #28) et on documente les kinds officiels ici.
KNOWN_KINDS: frozenset[str] = frozenset(
    {"duration_mismatch", "intro_mismatch", "title_drift"},
)


@dataclass(frozen=True)
class MatchSuspicion:
    """Une raison concrète de suspecter un mauvais match YT ↔ Acast.

    Attributs :
      - ``kind``     : famille du check qui a flaggué (str libre — voir
        ``KNOWN_KINDS`` pour les kinds officiels).
      - ``detail``   : message court humain (ex. ``"diff 23.4%"``).
      - ``severity`` : ``ERROR`` → flag ``matchSuspect=true`` ;
        ``WARNING`` → infos seulement.

    ``severity`` est OBLIGATOIRE (cf. CR archi #26 — un défaut ``error``
    silencieux était dangereux : un check warning oubliant de l'expliciter
    aurait flaggé à tort).
    """

    kind: str
    detail: str
    severity: Severity

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("MatchSuspicion.kind doit être une str non vide")
        if not isinstance(self.detail, str):
            raise ValueError("MatchSuspicion.detail doit être une str")
        if not isinstance(self.severity, Severity):
            raise ValueError(
                f"MatchSuspicion.severity doit être un Severity, "
                f"pas {type(self.severity).__name__}",
            )


def severity_value(sev: Severity | str) -> str:
    """Sérialise un ``Severity`` ou une str legacy en chaîne stable."""
    if isinstance(sev, Severity):
        return sev.value
    return str(sev)


def coerce_severity(value: Any) -> Severity:
    """Accepte ``Severity`` OU str (rétrocompat tests historiques)."""
    if isinstance(value, Severity):
        return value
    if isinstance(value, str):
        try:
            return Severity(value)
        except ValueError as exc:
            raise ValueError(f"Severity inconnue : {value!r}") from exc
    raise TypeError(f"Severity attend str/Severity, pas {type(value).__name__}")


__all__ = [
    "KNOWN_KINDS",
    "MatchSuspicion",
    "Severity",
    "coerce_severity",
    "severity_value",
]
