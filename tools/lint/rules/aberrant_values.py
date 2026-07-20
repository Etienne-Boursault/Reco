"""
aberrant_values.py — Détecte les valeurs hors-bornes ou syntaxiquement
invalides dans les recos / items / mentions.

Couvre :
  - year hors [year_min, year_max] (ERROR ; bornes injectables via
    ``LintSettings`` — CR senior H1, M6, CR archi #2/#5).
  - year non-int alors que présent (ERROR — CR senior H1).
  - year > today.year + 1 (WARNING — année future « légère », M6 ; date
    injectée, pas ``date.today()`` direct).
  - timestamp ``HH:MM:SS`` invalide (ERROR ; MM/SS ≥ 60, non-string…).
  - types vides ou inconnus (référencés par `ItemType` — calcul lazy H2).

La règle ``timestamp_unnormalized`` est séparée (CR senior C1) : un
timestamp ``MM:SS`` n'est PAS une erreur, juste un format pré-migration
qui devrait être normalisé en ``00:MM:SS`` (WARNING auto-fixable
potentiel).
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from .base import LintContext, LintIssue, LintRule, Severity
from ..settings import LintSettings

_TS_HHMMSS = re.compile(r"^(\d{2}):(\d{2}):(\d{2})$")
_TS_MMSS = re.compile(r"^(\d{1,2}):(\d{2})$")
_HARD_MAX_YEAR = 2100


def _classify_timestamp(value: Any) -> str:
    """Retourne ``"ok"`` / ``"unnormalized"`` / ``"invalid"``."""
    if not isinstance(value, str):
        return "invalid"
    m = _TS_HHMMSS.match(value)
    if m is not None:
        _, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return "ok" if (mm < 60 and ss < 60) else "invalid"
    m2 = _TS_MMSS.match(value)
    if m2 is not None:
        mm, ss = int(m2.group(1)), int(m2.group(2))
        if mm < 60 and ss < 60:
            return "unnormalized"
        return "invalid"
    return "invalid"


def _known_item_types() -> frozenset[str]:
    """Calcul lazy (H2) — évite la dépendance à l'import order de
    ``domain.item`` au chargement du module."""
    from domain.item import ItemType  # local import, H2
    return frozenset(t.value for t in ItemType)


class AberrantValuesRule(LintRule):
    name = "aberrant_values"
    severity = Severity.ERROR
    description = (
        "Valeurs hors bornes (year ∉ [year_min, year_max], timestamp ≠ "
        "HH:MM:SS, type inconnu)."
    )

    def __init__(
        self,
        settings: LintSettings | None = None,
        *,
        known_types: frozenset[str] | None = None,
    ) -> None:
        self._settings = settings or LintSettings()
        # H2 : DI explicite (test peut injecter, sinon calcul lazy).
        self._known_types_override = known_types

    @property
    def _known_types(self) -> frozenset[str]:
        if self._known_types_override is not None:
            return self._known_types_override
        return _known_item_types()

    def check(self, ctx: LintContext) -> Iterator[LintIssue]:
        for reco in ctx.recos:
            yield from self._check_reco(reco)

    # -- internal ------------------------------------------------------

    def _check_reco(self, reco: dict[str, Any]) -> Iterator[LintIssue]:
        eid = reco.get("id")
        entity_id = eid if isinstance(eid, str) and eid.strip() else "<unknown>"

        # --- year ----------------------------------------------------
        year = reco.get("year")
        if year is not None:
            if not isinstance(year, int) or isinstance(year, bool):
                # H1 : year non-int explicitement flagué.
                yield LintIssue(
                    rule=self.name, severity=Severity.ERROR,
                    entity_type="reco", entity_id=entity_id, field="year",
                    message=(
                        f"year non-int : {year!r} "
                        f"(type {type(year).__name__})"
                    ),
                )
            else:
                ymin = self._settings.year_min
                ymax = self._settings.year_max
                hard_max = _HARD_MAX_YEAR
                soft_max = self._settings.today.year + 1
                if year < ymin or year > hard_max:
                    yield LintIssue(
                        rule=self.name, severity=Severity.ERROR,
                        entity_type="reco", entity_id=entity_id, field="year",
                        message=(
                            f"year hors bornes : {year} (attendu "
                            f"[{ymin}, {hard_max}])"
                        ),
                    )
                elif year > ymax or year > soft_max:
                    # M6 : seuil soft → WARNING (paramétrable).
                    yield LintIssue(
                        rule=self.name, severity=Severity.WARNING,
                        entity_type="reco", entity_id=entity_id, field="year",
                        message=(
                            f"year > seuil soft ({year} > "
                            f"max({ymax}, today+1={soft_max}))"
                        ),
                    )

        # --- timestamp -----------------------------------------------
        ts = reco.get("timestamp")
        if ts is not None:
            kind = _classify_timestamp(ts)
            if kind == "invalid":
                yield LintIssue(
                    rule=self.name, severity=Severity.ERROR,
                    entity_type="reco", entity_id=entity_id, field="timestamp",
                    message=(
                        f"timestamp invalide : {ts!r} (attendu HH:MM:SS, "
                        "MM<60, SS<60)"
                    ),
                )
            elif kind == "unnormalized":
                # C1 : règle dédiée WARNING — auto-fixable en P2.
                yield LintIssue(
                    rule="timestamp_unnormalized",
                    severity=Severity.WARNING,
                    entity_type="reco", entity_id=entity_id, field="timestamp",
                    message=(
                        f"timestamp non normalisé MM:SS : {ts!r} "
                        "(devrait être 00:MM:SS)"
                    ),
                )

        # --- types ---------------------------------------------------
        types = reco.get("types")
        if types is None:
            return
        if not isinstance(types, (list, tuple)) or len(types) == 0:
            yield LintIssue(
                rule=self.name, severity=Severity.ERROR,
                entity_type="reco", entity_id=entity_id, field="types",
                message="types vide ou non-itérable",
            )
            return
        known = self._known_types
        for t in types:
            if not isinstance(t, str) or t not in known:
                yield LintIssue(
                    rule=self.name, severity=Severity.ERROR,
                    entity_type="reco", entity_id=entity_id, field="types",
                    message=(
                        f"type inconnu : {t!r} (attendu un de "
                        f"{sorted(known)})"
                    ),
                )


__all__ = ["AberrantValuesRule"]
