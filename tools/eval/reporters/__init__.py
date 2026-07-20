"""Reporters : exportent un ``EvalResult``/``EvalMetrics`` vers divers formats.

L'ajout d'un format = un nouveau module qui s'enregistre via
``@register_reporter("name")`` (cf. ``base.py``). Le CLI consomme
``REPORTERS`` sans connaître les implémentations.
"""
from __future__ import annotations

# L'import des modules concrets déclenche l'auto-enregistrement.
from tools.eval.reporters.base import REPORTERS, EvalReporter, register_reporter
from tools.eval.reporters.csv_reporter import (
    CsvReporter,
    render_csv,
    write_csv,
)
from tools.eval.reporters.markdown_reporter import (
    MarkdownReporter,
    render_markdown,
    write_markdown,
)

__all__ = [
    "CsvReporter",
    "EvalReporter",
    "MarkdownReporter",
    "REPORTERS",
    "register_reporter",
    "render_csv",
    "render_markdown",
    "write_csv",
    "write_markdown",
]
