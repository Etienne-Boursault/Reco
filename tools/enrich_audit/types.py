"""enrich_audit.types — Value Objects, Protocols, enums.

Module dédié pour les VOs et contrats du package `enrich_audit` :
on garde `service.py` strictement orchestrateur (cf. CR archi P2 #4).

Aligné CR senior :
- **M1** : `Severity` StrEnum à la place de `score` numérique inversé.
- **C5** : `Check(Protocol)` typé (name, kind, description, __call__).
- **C4** : `TmdbPayload` type alias + `TMDB_CACHE_VERSION` constant.
- **#14 archi** : `SidecarPayload` versionné (`schemaVersion`, `auditedAt`,
  `auditorVersion`).

Pure — aucune IO ni dépendance externe.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, Protocol, runtime_checkable

from audit_core.types import Severity  # SSOT — cf. ADR 0019
from domain.item import Item

# ---------------------------------------------------------------------------
# Versioning / constants exposés (CR archi P3 #19)
# ---------------------------------------------------------------------------

#: Version du payload TMDB cache attendue (cf. CR senior C4).
TMDB_CACHE_VERSION: Final[int] = 1

#: Version du schéma sidecar (cf. CR archi #14).
SIDECAR_SCHEMA_VERSION: Final[int] = 1

#: Version du moteur d'audit lui-même (semver-lite, bump à chaque évolution
#: sémantique des checks). Stockée dans chaque sidecar pour ré-enrich
#: proactif Phase 2 #17.
AUDITOR_VERSION: Final[str] = "0.2.0"

#: TMDB kind autorisé (movie | tv). `Literal` plutôt que StrEnum pour
#: rester aligné avec `ExternalIds.tmdb_type` (str brute "movie"/"tv").
TmdbKind = Literal["movie", "tv"]

#: Payload TMDB brut tel qu'on l'attend dans le cache. On le type comme
#: un dict permissif (TMDB renvoie >100 clés). Les checks lisent les clés
#: qu'ils savent traiter ; les autres sont ignorées.
TmdbPayload = Mapping[str, object]


# ---------------------------------------------------------------------------
# Severity (CR senior M1) — réexport audit_core (ADR 0019)
# ---------------------------------------------------------------------------

# Note ADR 0019 : ``Severity`` est désormais réexporté depuis
# ``audit_core.types`` (option B — 4 niveaux unifiés ``INFO``, ``WARNING``,
# ``ERROR``, ``CRITICAL``). enrich_audit conserve la même sémantique :
# - INFO     : signal faible (court probable, à vérifier)
# - WARNING  : anomalie probable
# - CRITICAL : mismatch quasi-certain (type TMDB ≠ type Item, year delta > 10)
# ``ERROR`` n'est pas émis par les checks enrich_audit mais reste accessible
# (forward-compat).


# ---------------------------------------------------------------------------
# Suspicion (VO)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Suspicion:
    """Drapeau levé par un check sur un item donné.

    Attributs :
        kind: identifiant stable du check (``"title_mismatch"``…).
        detail: message humain — pour reporter et debugger.
        severity: gravité (cf. `Severity`). Par défaut WARNING.
        confidence: confiance optionnelle ∈ [0, 1] — convention naturelle
            (1.0 = très confiant). ``None`` quand non applicable.
    """

    kind: str
    detail: str
    severity: Severity = Severity.WARNING
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.kind or not isinstance(self.kind, str):
            raise ValueError("Suspicion.kind doit être une str non vide")
        if not isinstance(self.detail, str):
            raise ValueError("Suspicion.detail doit être une str")
        if not isinstance(self.severity, Severity):
            raise ValueError(
                f"Suspicion.severity doit être un Severity, "
                f"reçu {type(self.severity).__name__}"
            )
        if self.confidence is not None:
            # bool est subclass int → exclure explicitement (CR senior L13)
            if not isinstance(self.confidence, (int, float)) or isinstance(
                self.confidence, bool
            ):
                raise ValueError("Suspicion.confidence doit être un nombre ou None")
            if not (0.0 <= float(self.confidence) <= 1.0):
                raise ValueError(
                    f"Suspicion.confidence hors borne [0,1]: {self.confidence}"
                )


# ---------------------------------------------------------------------------
# Check (Protocol — CR archi P0 #1)
# ---------------------------------------------------------------------------


@runtime_checkable
class Check(Protocol):
    """Contrat d'un check.

    Un check est une callable structurelle (Protocol) qui expose :
      - ``name`` : identifiant lisible (slug snake_case).
      - ``kind`` : ``Suspicion.kind`` émis (1 check ⇔ 1 kind par convention).
      - ``description`` : phrase courte — utile pour reporter & docs.

    Et un ``__call__(item, tmdb_data) -> Suspicion | None``.

    Les fonctions historiques (``check_title_similarity`` etc.) sont wrappées
    via ``FunctionCheck`` ci-dessous pour conformer rétro-actif.
    """

    name: str
    kind: str
    description: str

    def __call__(
        self, item: Item, tmdb_data: TmdbPayload
    ) -> Suspicion | None: ...  # pragma: no cover — Protocol contract


__all__ = [
    "AUDITOR_VERSION",
    "Check",
    "Severity",
    "SIDECAR_SCHEMA_VERSION",
    "Suspicion",
    "TMDB_CACHE_VERSION",
    "TmdbKind",
    "TmdbPayload",
]
