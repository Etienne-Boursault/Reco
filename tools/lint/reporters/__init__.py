"""
reporters — Formatage humain/machine des `LintReport`.

Séparation explicite (SRP) : le service ne sait pas formater, les règles
ne savent pas formater. Ce module isole la cosmétique.

CR archi #7 : registry plug-in — chaque reporter expose ``format_id``
et ``render(report) -> str``. La CLI choisit via ``--format``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .json_reporter import JsonReporter
from .json_reporter import render as render_json
from .markdown_reporter import MarkdownReporter
from .markdown_reporter import render as render_markdown
from .summary import build_summary

if TYPE_CHECKING:  # pragma: no cover
    from ..service import LintReport


class Reporter(Protocol):
    """Protocol d'un reporter (P1 #7)."""

    format_id: str

    def render(self, report: LintReport) -> str: ...


REPORTERS: dict[str, Reporter] = {
    "markdown": MarkdownReporter(),
    "json": JsonReporter(),
}


def get_reporter(format_id: str) -> Reporter:
    """Renvoie le reporter du format demandé. ValueError si inconnu."""
    try:
        return REPORTERS[format_id]
    except KeyError as exc:
        raise ValueError(
            f"format inconnu : {format_id!r} (disponibles : "
            f"{sorted(REPORTERS)})"
        ) from exc


__all__ = [
    "REPORTERS",
    "JsonReporter",
    "MarkdownReporter",
    "Reporter",
    "build_summary",
    "get_reporter",
    "render_json",
    "render_markdown",
]
