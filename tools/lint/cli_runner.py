"""
cli_runner.py — Logique métier extraite du CLI (CR archi #9).

Pattern copié de ``tools/enrich_audit/cli_runner.py``. La fine couche
argparse vit dans ``tools/lint_dataset.py`` ; tout le reste est ici,
testable sans subprocess.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .loaders import DatasetLoader
from .reporters import Reporter, get_reporter
from .rules import default_rules
from .rules.base import LintIssue, Severity
from .service import LintReport, LintService
from .settings import LintSettings


@dataclass(frozen=True)
class LintRunOptions:
    """Options d'un run de lint."""

    source_id: str
    output: Path
    severity_filter: Severity | None = None
    rule_filter: str | None = None
    reporter: Reporter | None = None
    loader: DatasetLoader | None = None
    settings: LintSettings | None = None


@dataclass(frozen=True)
class LintRunResult:
    """Sortie d'un run : rapport, chemin de sortie, durée, exit code."""

    report: LintReport
    output_path: Path
    duration_s: float
    exit_code: int


def _compute_exit_code(report: LintReport) -> int:
    """Exit code calculé sur les compteurs ``*_unfiltered`` (CR H9).

    Le filtrage CLI est cosmétique — un linter qui mute son exit code
    selon la vue choisie est un linter qui ment.
    """
    if report.n_errors_unfiltered > 0:
        return 1
    if report.n_warnings_unfiltered > 0:
        return 2
    return 0


def run_lint(opts: LintRunOptions) -> LintRunResult:
    """Exécute le lint complet : charge → exécute → filtre → écrit."""
    from tools.common import atomic_write_text  # L8 (import paresseux)

    if opts.loader is None:
        raise ValueError("LintRunOptions.loader est requis")
    reporter = opts.reporter or get_reporter("markdown")
    settings = opts.settings or LintSettings()

    t0 = time.perf_counter()
    ctx, io_issues = opts.loader.load(opts.source_id)
    svc = LintService(default_rules(settings))
    report = svc.run(ctx)
    # H7 : incorporer les issues IO synthétiques au rapport.
    if io_issues:
        report = LintReport.from_issues(
            tuple(report.issues) + tuple(io_issues),
        )
    filtered = report.filter(
        severity=opts.severity_filter, rule=opts.rule_filter,
    )
    rendered = reporter.render(filtered)
    opts.output.parent.mkdir(parents=True, exist_ok=True)
    # L8 : atomic_write_text au lieu de Path.write_text direct.
    atomic_write_text(opts.output, rendered)
    duration = time.perf_counter() - t0
    exit_code = _compute_exit_code(filtered)
    return LintRunResult(
        report=filtered, output_path=opts.output,
        duration_s=duration, exit_code=exit_code,
    )


__all__ = [
    "LintRunOptions",
    "LintRunResult",
    "run_lint",
    "_compute_exit_code",
]
