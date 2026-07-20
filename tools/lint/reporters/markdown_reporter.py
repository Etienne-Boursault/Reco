"""
markdown_reporter.py — Rendu Markdown d'un `LintReport`.

Sortie déterministe (clés triées, ordre stable des règles) pour faciliter
les diffs CI et la lecture humaine.

M3 : les messages utilisateur peuvent contenir des backticks / astérisques
(extraction LLM bruyante). On les *escape* dans le rendu pour éviter
qu'un `**` se transforme en gras ou qu'un backtick non-fermé casse le
bloc de code.
"""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from audit_core.reporters import escape_md as _escape_md

from ..rules.base import LintIssue, Severity
from .summary import build_summary

if TYPE_CHECKING:  # pragma: no cover
    from ..service import LintReport

_SEVERITY_ORDER = (Severity.ERROR, Severity.WARNING, Severity.INFO)
_SEVERITY_LABEL = {
    Severity.ERROR: "Errors",
    Severity.WARNING: "Warnings",
    Severity.INFO: "Infos",
}

# Note ADR 0019 : ``_escape_md`` est désormais réexporté depuis
# ``audit_core.reporters.escape_md`` (union complète : `\, *, _, backtick,
# [, ], |, \n, \r`). Le linter gagne `|`, `\n`, `\r` sans casser ses tests
# existants (qui ne vérifient que `, *).


def _format_issue(issue: LintIssue) -> str:
    field_part = f" · `{_escape_md(issue.field)}`" if issue.field else ""
    return (
        f"- `{_escape_md(issue.entity_type)}/{_escape_md(issue.entity_id)}`"
        f"{field_part} — {_escape_md(issue.message)}"
    )


def render(report: "LintReport") -> str:
    """Rend un rapport en Markdown.

    Sections : Summary → par sévérité (Error, Warning, Info) →
    sous-groupé par règle pour limiter le bruit.
    """
    summary = build_summary(report)
    lines: list[str] = []
    lines.append("# Dataset Lint Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total issues : **{summary.n_total}**")
    lines.append(f"- Errors       : **{summary.n_errors}**")
    lines.append(f"- Warnings     : **{summary.n_warnings}**")
    lines.append(f"- Infos        : **{summary.n_infos}**")
    lines.append("")
    if summary.top_rules:
        lines.append("### Top rules")
        lines.append("")
        for name, count in summary.top_rules:
            lines.append(f"- `{name}` : {count}")
        lines.append("")

    by_sev: dict[Severity, list[LintIssue]] = defaultdict(list)
    for issue in report.issues:
        by_sev[issue.severity].append(issue)

    for sev in _SEVERITY_ORDER:
        bucket = by_sev.get(sev, [])
        if not bucket:
            continue
        lines.append(f"## {_SEVERITY_LABEL[sev]} ({len(bucket)})")
        lines.append("")
        by_rule: dict[str, list[LintIssue]] = defaultdict(list)
        for issue in bucket:
            by_rule[issue.rule].append(issue)
        for rule_name in sorted(by_rule):
            issues = by_rule[rule_name]
            lines.append(f"### `{rule_name}` ({len(issues)})")
            lines.append("")
            for issue in sorted(
                issues, key=lambda i: (i.entity_id, i.field or "")
            ):
                lines.append(_format_issue(issue))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


class MarkdownReporter:
    """Reporter format Markdown (registry-compatible — P1 #7/#8)."""

    format_id = "markdown"

    def render(self, report: "LintReport") -> str:
        return render(report)


__all__ = ["render", "MarkdownReporter"]
