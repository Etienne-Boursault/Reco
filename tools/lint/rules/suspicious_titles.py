"""
suspicious_titles.py — Détecte les titres louches (extraction sale,
artefact transcript, format aberrant).

Heuristiques (warning, pas error : peuvent être de vrais titres) :
  - longueur < ``title_min_len`` ou > ``title_max_len`` (H3 paramétrable).
  - tout en majuscules (>``title_caps_threshold`` chars).
  - contient ``[``, ``]``, ``<``, ``>`` (probable artefact extraction LLM).
  - matche un des patterns ``title_suspicious_patterns`` injectés (CR
    archi #5 — *source-aware*, ne hardcode plus le FR « un-bon-moment »).

Couvre aussi ``ctx.items`` (CR senior M4) — pas seulement les recos.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from typing import Any

from .base import LintContext, LintIssue, LintRule, Severity
from ..settings import LintSettings

_BRACKET_CHARS = frozenset("[]<>")


def _normalize(value: str) -> str:
    """NFKC + strip — pour comparaison stable (H8)."""
    return unicodedata.normalize("NFKC", value).strip()


class SuspiciousTitlesRule(LintRule):
    name = "suspicious_titles"
    severity = Severity.WARNING
    description = (
        "Titre louche (trop court/long, tout en majuscules, brackets, "
        "suffixes de format injectés)."
    )

    def __init__(
        self,
        settings: LintSettings | None = None,
        *,
        # H3 — overrides explicites pour les tests qui ne veulent pas
        # construire un LintSettings complet.
        min_len: int | None = None,
        max_len: int | None = None,
        all_caps_threshold: int | None = None,
        extra_patterns: tuple[str, ...] = (),
    ) -> None:
        self._settings = settings or LintSettings()
        self._min_len = min_len if min_len is not None else self._settings.title_min_len
        self._max_len = max_len if max_len is not None else self._settings.title_max_len
        self._caps = (
            all_caps_threshold if all_caps_threshold is not None
            else self._settings.title_caps_threshold
        )
        patterns = tuple(self._settings.title_suspicious_patterns) + tuple(extra_patterns)
        self._patterns: tuple[re.Pattern[str], ...] = tuple(
            re.compile(p, re.IGNORECASE) for p in patterns
        )

    def check(self, ctx: LintContext) -> Iterator[LintIssue]:
        for reco in ctx.recos:
            eid_value = reco.get("id")
            eid = (
                eid_value if isinstance(eid_value, str) and eid_value.strip()
                else "<unknown>"
            )
            if ctx.is_overridden(entity_id=eid, field="title"):
                continue
            yield from self._iter_title_issues(
                title=reco.get("title"), entity_type="reco", entity_id=eid,
            )
        # M4 : couvrir aussi les Items (œuvres typées).
        for item in ctx.items:
            if ctx.is_overridden(entity_id=item.id, field="title"):
                continue
            yield from self._iter_title_issues(
                title=item.title, entity_type="item", entity_id=item.id,
            )

    # -- internal ------------------------------------------------------

    def _iter_title_issues(
        self, *, title: Any, entity_type: str, entity_id: str,
    ) -> Iterator[LintIssue]:
        if not isinstance(title, str):
            return
        stripped = _normalize(title)
        if not stripped:
            return  # required_fields s'en charge

        n = len(stripped)
        if n < self._min_len:
            yield LintIssue(
                rule=self.name, severity=self.severity, entity_type=entity_type,
                entity_id=entity_id, field="title",
                message=f"titre trop court ({n} chars) : {title!r}",
            )
        if n > self._max_len:
            yield LintIssue(
                rule=self.name, severity=self.severity, entity_type=entity_type,
                entity_id=entity_id, field="title",
                message=f"titre trop long ({n} chars) : {title[:60]!r}…",
            )
        if (
            n > self._caps
            and stripped == stripped.upper()
            and stripped != stripped.lower()
        ):
            yield LintIssue(
                rule=self.name, severity=self.severity, entity_type=entity_type,
                entity_id=entity_id, field="title",
                message=f"titre tout en majuscules : {title!r}",
            )
        if any(c in _BRACKET_CHARS for c in stripped):
            yield LintIssue(
                rule=self.name, severity=self.severity, entity_type=entity_type,
                entity_id=entity_id, field="title",
                message=f"titre contient `[`/`]`/`<`/`>` (artefact extraction) : {title!r}",
            )
        for pat in self._patterns:
            if pat.search(stripped):
                yield LintIssue(
                    rule=self.name, severity=self.severity, entity_type=entity_type,
                    entity_id=entity_id, field="title",
                    message=(
                        f"titre matche un suffixe de format suspect "
                        f"({pat.pattern!r}) : {title!r}"
                    ),
                )
                break


__all__ = ["SuspiciousTitlesRule"]
