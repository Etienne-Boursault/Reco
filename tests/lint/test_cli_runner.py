"""Tests TDD pour `tools.lint.cli_runner` (CR archi #9)."""
from __future__ import annotations

from pathlib import Path

import pytest

from lint.cli_runner import LintRunOptions, _compute_exit_code, run_lint
from lint.loaders import DatasetLoader
from lint.reporters import get_reporter
from lint.rules.base import LintContext, LintIssue, Severity
from lint.service import LintReport
from lint.settings import LintSettings


class _FakeLoader:
    def __init__(self, ctx: LintContext, io_issues: tuple[LintIssue, ...] = ()):
        self._ctx = ctx
        self._io = io_issues

    def load(self, source_id: str):
        return self._ctx, self._io


def test_run_lint_writes_markdown_by_default(tmp_path):
    out = tmp_path / "report.md"
    loader = _FakeLoader(LintContext(source_id="ubm"))
    opts = LintRunOptions(
        source_id="ubm", output=out, loader=loader,
    )
    result = run_lint(opts)
    assert out.exists()
    assert "Dataset Lint Report" in out.read_text(encoding="utf-8")
    assert result.exit_code == 0
    assert result.duration_s >= 0


def test_run_lint_supports_json_reporter(tmp_path):
    out = tmp_path / "report.json"
    loader = _FakeLoader(LintContext(source_id="ubm"))
    opts = LintRunOptions(
        source_id="ubm", output=out, loader=loader,
        reporter=get_reporter("json"),
    )
    result = run_lint(opts)
    assert out.exists()
    import json
    first = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert first["kind"] == "meta"
    assert result.exit_code == 0


def test_run_lint_requires_loader(tmp_path):
    with pytest.raises(ValueError):
        run_lint(LintRunOptions(source_id="ubm", output=tmp_path / "x.md"))


def test_run_lint_propagates_io_issues_to_report(tmp_path):
    """H7 : les issues IO du loader sont injectés au rapport final."""
    io = (LintIssue(
        rule="dataset_io", severity=Severity.WARNING,
        entity_type="dataset", entity_id="bad.json", field=None,
        message="cassé",
    ),)
    loader = _FakeLoader(LintContext(source_id="ubm"), io_issues=io)
    opts = LintRunOptions(
        source_id="ubm", output=tmp_path / "r.md", loader=loader,
    )
    result = run_lint(opts)
    assert result.exit_code == 2  # warnings only
    md = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "dataset_io" in md


def test_run_lint_filter_does_not_alter_exit_code(tmp_path):
    """H9 : le filtre est cosmétique."""
    io = (LintIssue(
        rule="dataset_io", severity=Severity.ERROR,
        entity_type="dataset", entity_id="x", field=None, message="m",
    ),)
    loader = _FakeLoader(LintContext(source_id="ubm"), io_issues=io)
    opts = LintRunOptions(
        source_id="ubm", output=tmp_path / "r.md", loader=loader,
        severity_filter=Severity.WARNING,  # masque les errors visuellement
    )
    result = run_lint(opts)
    # Même filtré, l'erreur réelle existe → exit 1.
    assert result.exit_code == 1


def test_compute_exit_code_unfiltered_priority():
    """H9 : se base sur `n_errors_unfiltered` quand présent."""
    issues = (LintIssue(
        rule="r", severity=Severity.ERROR, entity_type="reco",
        entity_id="x", field=None, message="m",
    ),)
    report = LintReport.from_issues(issues)
    assert _compute_exit_code(report) == 1


def test_run_lint_uses_settings_for_rule_selection(tmp_path):
    """CR archi #2 : settings.disabled_rules filtre les règles."""
    out = tmp_path / "r.md"
    loader = _FakeLoader(LintContext(source_id="ubm"))
    # Si on désactive TOUTES les règles, le rapport est vide.
    opts = LintRunOptions(
        source_id="ubm", output=out, loader=loader,
        settings=LintSettings(enabled_rules=()),  # whitelist vide
    )
    result = run_lint(opts)
    assert result.report.n_total == 0


def test_protocol_loader_can_be_substituted(tmp_path):
    """LSP : tout Protocol-compliant est accepté."""
    class _MinimalLoader:
        def load(self, source_id):
            return LintContext(source_id="ubm"), ()

    assert isinstance(_MinimalLoader(), DatasetLoader)
    opts = LintRunOptions(
        source_id="ubm", output=tmp_path / "r.md",
        loader=_MinimalLoader(),
    )
    result = run_lint(opts)
    assert result.exit_code == 0
