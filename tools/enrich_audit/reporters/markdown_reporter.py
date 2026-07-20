"""Reporter Markdown.

CR senior :
- **M5** : échappe ``\\n``, ``|``, backticks dans les champs interpolés
  pour éviter l'injection markdown.
- **L4** : tri stable des résultats par ``item_id``.
"""
from __future__ import annotations

from audit_core.reporters import escape_md as _md_escape  # SSOT — ADR 0019 S-03

from ..service import SourceAuditReport

# Note ADR 0019 (S-03) : ``_md_escape`` est désormais réexporté depuis
# ``audit_core.reporters.escape_md`` (union complète : `\, *, _, backtick,
# [, ], |, \n→space, \r→space`). enrich_audit gagne `*`, `_`, `[`, `]`
# qui n'étaient pas échappés avant — couvre les nouveaux cas (titres
# avec markdown bruyant venant de TMDB).


def format_markdown(report: SourceAuditReport) -> str:
    """Rapport Markdown court — lisible CLI ou copier-coller."""
    lines = [
        f"# Audit TMDB — `{_md_escape(report.source_id)}`",
        "",
        f"- Items audités : **{report.audited_count}**",
        f"- Suspects : **{report.suspect_count}**",
        f"- Clean : **{report.clean_count}**",
        f"- Skipped (sans tmdb) : {report.skipped_no_tmdb}",
        f"- Skipped (sans cache) : {report.skipped_no_cache}",
    ]
    if report.skipped_check_error:
        lines.append(f"- Check errors : {report.skipped_check_error}")
    if report.skipped_cache_version_mismatch:
        lines.append(
            f"- Skipped (cache version mismatch) : "
            f"{report.skipped_cache_version_mismatch}"
        )
    lines.append("")
    if report.suspect_count == 0:
        lines.append("Aucun item suspect.")
        return "\n".join(lines) + "\n"
    lines.append("## Items suspects")
    lines.append("")
    # CR senior L4 : tri stable par item_id.
    sorted_results = sorted(report.results, key=lambda r: r.item_id)
    for r in sorted_results:
        if not r.is_suspect:
            continue
        lines.append(f"### `{_md_escape(r.item_id)}`")
        for s in r.suspicions:
            sev = s.severity.value.upper()
            lines.append(
                f"- **[{sev}] {_md_escape(s.kind)}** : {_md_escape(s.detail)}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


__all__ = ["format_markdown"]
