"""
json_reporter.py — Rendu JSONL/JSON d'un `LintReport` (CR senior H10,
CR archi #11/#7).

Une ligne JSON par issue (JSONL) — facile à grepper, à pipe vers
``jq``, à charger en pandas. La tête du fichier est un objet ``meta``
avec les compteurs agrégés.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ..rules.base import LintIssue

if TYPE_CHECKING:  # pragma: no cover
    from ..service import LintReport


def _issue_to_dict(issue: LintIssue) -> dict[str, Any]:
    return {
        "rule": issue.rule,
        "severity": issue.severity.value,
        "entityType": issue.entity_type,
        "entityId": issue.entity_id,
        "field": issue.field,
        "message": issue.message,
        "clusterId": issue.cluster_id,
    }


def render(report: "LintReport") -> str:
    """JSONL : 1 ligne meta + 1 ligne par issue, terminé par \\n."""
    lines: list[str] = []
    meta = {
        "kind": "meta",
        "total": report.n_total,
        "errors": report.n_errors,
        "warnings": report.n_warnings,
        "infos": report.n_infos,
        "byRule": dict(report.n_by_rule),
        "errorsUnfiltered": report.n_errors_unfiltered,
        "warningsUnfiltered": report.n_warnings_unfiltered,
    }
    lines.append(json.dumps(meta, ensure_ascii=False, sort_keys=True))
    for issue in sorted(
        report.issues,
        key=lambda i: (i.severity.value, i.rule, i.entity_id, i.field or ""),
    ):
        payload = {"kind": "issue", **_issue_to_dict(issue)}
        lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return "\n".join(lines) + "\n"


class JsonReporter:
    """Reporter format JSONL (registry-compatible — P1 #7)."""

    format_id = "json"

    def render(self, report: "LintReport") -> str:
        return render(report)


__all__ = ["render", "JsonReporter"]
