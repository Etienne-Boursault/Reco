"""
summary.py — Stats top-level d'un `LintReport`.

Pure : ne formate rien (le markdown_reporter consomme ces stats).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..rules.base import Severity

if TYPE_CHECKING:  # pragma: no cover
    from ..service import LintReport


@dataclass(frozen=True)
class LintSummary:
    """Stats agrégées d'un rapport."""

    n_total: int
    n_errors: int
    n_warnings: int
    n_infos: int
    top_rules: tuple[tuple[str, int], ...]
    """Top règles violées, triées par count desc puis nom asc."""


def build_summary(report: "LintReport", *, top_n: int = 5) -> LintSummary:
    """Construit un `LintSummary` depuis un `LintReport`.

    Top-N : tri stable (count desc puis nom asc — déterministe pour CI).
    Le rapport est tapé `Any` car l'import croisé service↔reporters
    serait circulaire. Le contrat n'utilise que `n_by_severity` et
    `n_by_rule`.
    """
    sev = report.n_by_severity
    rule_counts = sorted(
        report.n_by_rule.items(),
        key=lambda kv: (-kv[1], kv[0]),
    )[:top_n]
    return LintSummary(
        n_total=report.n_total,
        n_errors=sev.get(Severity.ERROR, 0),
        n_warnings=sev.get(Severity.WARNING, 0),
        n_infos=sev.get(Severity.INFO, 0),
        top_rules=tuple(rule_counts),
    )


__all__ = ["LintSummary", "build_summary"]
