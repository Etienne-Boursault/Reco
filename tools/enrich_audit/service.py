"""enrich_audit.service — orchestrateur d'audit post-enrichissement TMDB.

Service qui exécute une liste de checks injectés (SOLID/OCP : on étend en
ajoutant un check au pipeline sans modifier le service).

Pure logique — aucune IO. La récupération des données TMDB est déléguée
à un provider passé en paramètre (test injection, cache, API…).

Les VOs (`Suspicion`, `Severity`, `Check`, `TmdbPayload`) vivent dans
`tools.enrich_audit.types` (CR archi P2 #4 — séparation VOs vs service).

Compat rétro :
- `Suspicion`, `Severity`, `Check`, `TmdbPayload` ré-exportés.
- `CheckFunction` (alias Callable hérité) ré-exporté en dépréciation douce.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from domain.item import Item

from .types import (
    Check,
    Severity,
    Suspicion,
    TmdbPayload,
)

_log = logging.getLogger("reco.enrich_audit")


# ---------------------------------------------------------------------------
# Result VOs (restent ici — couplés à l'orchestration)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditResult:
    """Verdict pour un item donné — agrégat des suspicions levées."""

    item_id: str
    is_suspect: bool
    suspicions: tuple[Suspicion, ...] = ()

    def __post_init__(self) -> None:
        if not self.item_id or not isinstance(self.item_id, str):
            raise ValueError("AuditResult.item_id doit être une str non vide")
        if not isinstance(self.suspicions, tuple):
            raise ValueError("AuditResult.suspicions doit être un tuple")
        # Invariant : is_suspect ⇔ suspicions non vide.
        if self.is_suspect != bool(self.suspicions):
            raise ValueError(
                f"AuditResult.is_suspect={self.is_suspect} incohérent "
                f"avec len(suspicions)={len(self.suspicions)}"
            )


@dataclass(frozen=True, slots=True)
class SourceAuditReport:
    """Verdict pour une source entière."""

    source_id: str
    results: tuple[AuditResult, ...] = ()
    skipped_no_tmdb: int = 0
    skipped_no_cache: int = 0
    skipped_check_error: int = 0
    skipped_cache_version_mismatch: int = 0
    sidecar_malformed: int = 0

    @property
    def suspect_count(self) -> int:
        return sum(1 for r in self.results if r.is_suspect)

    @property
    def clean_count(self) -> int:
        return sum(1 for r in self.results if not r.is_suspect)

    @property
    def audited_count(self) -> int:
        return len(self.results)


# ---------------------------------------------------------------------------
# Provider type (TMDB data → dict | None)
# ---------------------------------------------------------------------------


#: Provider qui rend les données TMDB brutes pour un tmdb_id donné.
#: Renvoie ``None`` si non disponible (cache absent / API offline / mock vide).
#: Signature historiquement int → dict | None ; le nouveau signal `tmdb_type`
#: passe par `item.external_ids.tmdb_type` côté checks (cf. CR senior C5).
TmdbDataProvider = Callable[[int], "dict | None"]


# Alias historique — déprécié soft (CR archi P0 #1).
# Préférer `tools.enrich_audit.types.Check`.
CheckFunction = Callable[[Item, TmdbPayload], "Suspicion | None"]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EnrichAuditService:
    """Audit d'enrichissement TMDB par composition de checks.

    Args:
        checks: itérable de callables (ou `Check` Protocol) exécutés dans
            l'ordre. Le service ne sait rien de leur logique (OCP : ajouter
            un check = ajouter une entrée à la liste).

    CR senior H6 : chaque check est exécuté dans un try/except — une
    exception dans un check ne fait pas crasher tout l'audit. Le compteur
    `skipped_check_error` du rapport trace les incidents.
    """

    def __init__(self, checks: Iterable[Check | CheckFunction]) -> None:
        checks_list = tuple(checks)
        if not checks_list:
            raise ValueError("EnrichAuditService : au moins un check requis")
        self._checks: tuple[Check | CheckFunction, ...] = checks_list

    # -- API ----------------------------------------------------------------

    def _run_checks(
        self,
        item: Item,
        tmdb_data: TmdbPayload,
    ) -> tuple[list[Suspicion], int]:
        """Exécute tous les checks. Retourne (suspicions, nb_erreurs)."""
        suspicions: list[Suspicion] = []
        errors = 0
        for check in self._checks:
            try:
                result = check(item, tmdb_data)
            except Exception:  # noqa: BLE001 — isolation explicite voulue
                check_name = getattr(check, "name", getattr(check, "__name__", repr(check)))
                _log.warning(
                    "Check %s a levé une exception sur item %s — skip",
                    check_name, item.id, exc_info=True,
                )
                errors += 1
                continue
            if result is not None:
                suspicions.append(result)
        return suspicions, errors

    def audit_item(
        self,
        item: Item,
        tmdb_data_provider: TmdbDataProvider,
    ) -> AuditResult | None:
        """Audite un item.

        Returns:
            - ``None`` si l'item n'a pas d'``external_ids.tmdb`` (rien à
              auditer — on ne génère pas de verdict).
            - ``None`` également si le provider renvoie ``None`` (cache
              absent).
            - ``AuditResult`` sinon (clean ou suspect).

        Note : pour distinguer les trois cas `None` (no_tmdb / no_cache /
        no_suspicions clean) côté caller, préférer `audit_items()` qui
        tient les compteurs séparés (CR senior L6).
        """
        tmdb_id = item.external_ids.tmdb
        if tmdb_id is None:
            return None
        tmdb_data = tmdb_data_provider(tmdb_id)
        if tmdb_data is None:
            return None

        suspicions, _errors = self._run_checks(item, tmdb_data)
        suspicions_t = tuple(suspicions)
        return AuditResult(
            item_id=item.id,
            is_suspect=bool(suspicions_t),
            suspicions=suspicions_t,
        )

    def audit_items(
        self,
        source_id: str,
        items: Iterable[Item],
        tmdb_data_provider: TmdbDataProvider,
    ) -> SourceAuditReport:
        """Audite tous les items d'une source.

        Items sans ``tmdb`` ou sans cache → comptabilisés mais non auditeés.
        """
        results: list[AuditResult] = []
        skipped_no_tmdb = 0
        skipped_no_cache = 0
        skipped_check_error_items = 0
        for item in items:
            if item.external_ids.tmdb is None:
                skipped_no_tmdb += 1
                continue
            data = tmdb_data_provider(item.external_ids.tmdb)
            if data is None:
                skipped_no_cache += 1
                continue

            suspicions, errors = self._run_checks(item, data)
            if errors:
                skipped_check_error_items += errors
            suspicions_t = tuple(suspicions)
            results.append(AuditResult(
                item_id=item.id,
                is_suspect=bool(suspicions_t),
                suspicions=suspicions_t,
            ))

        return SourceAuditReport(
            source_id=source_id,
            results=tuple(results),
            skipped_no_tmdb=skipped_no_tmdb,
            skipped_no_cache=skipped_no_cache,
            skipped_check_error=skipped_check_error_items,
        )


__all__ = [
    "AuditResult",
    "Check",
    "CheckFunction",
    "EnrichAuditService",
    "Severity",
    "SourceAuditReport",
    "Suspicion",
    "TmdbDataProvider",
    "TmdbPayload",
]
