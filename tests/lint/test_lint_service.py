"""Tests TDD pour `LintService` et `LintReport` (post-H5/H9/L5/#8/#14)."""
from __future__ import annotations

import pytest

from lint.rules.base import LintContext, LintIssue, Severity
from lint.service import LintReport, LintService


class _AlwaysFails:
    name = "always_fails"
    severity = Severity.ERROR
    description = "Émet toujours un issue."

    def __init__(self, n: int = 1):
        self._n = n

    def check(self, ctx):
        for i in range(self._n):
            yield LintIssue(
                rule=self.name, severity=self.severity, entity_type="reco",
                entity_id=f"x-{i}", field="title", message="fail",
            )


class _AlwaysClean:
    name = "always_clean"
    severity = Severity.WARNING
    description = "N'émet rien."

    def check(self, ctx):
        return iter(())


def test_service_runs_all_rules_and_aggregates():
    svc = LintService([_AlwaysFails(2), _AlwaysClean()])
    report = svc.run(LintContext(source_id="ubm"))
    assert report.n_total == 2
    assert report.n_errors == 2
    assert report.n_warnings == 0


def test_service_rejects_non_lintrule():
    with pytest.raises(TypeError):
        LintService([object()])  # type: ignore[list-item]


def test_service_run_rejects_primitive_ctx():
    """H5 : on duck-type, mais une str primitive est manifestement fausse."""
    svc = LintService([_AlwaysClean()])
    with pytest.raises(TypeError):
        svc.run("not a context")  # type: ignore[arg-type]


def test_service_run_accepts_duck_typed_ctx_for_lsp():
    """H5 : LSP — un substitut qui expose `.recos` + `.episodes` passe."""

    class _DuckCtx:
        recos = ()
        episodes = ()

    svc = LintService([_AlwaysClean()])
    report = svc.run(_DuckCtx())  # type: ignore[arg-type]
    assert report.n_total == 0


def test_service_run_rejects_ctx_missing_attrs():
    """H5 : objet sans `recos` / `episodes` rejeté."""

    class _Bad:
        pass

    svc = LintService([_AlwaysClean()])
    with pytest.raises(TypeError):
        svc.run(_Bad())  # type: ignore[arg-type]


def test_service_run_is_idempotent():
    svc = LintService([_AlwaysFails(1)])
    ctx = LintContext(source_id="ubm")
    r1 = svc.run(ctx)
    r2 = svc.run(ctx)
    assert r1.n_total == r2.n_total == 1


def test_service_rules_property_is_tuple():
    svc = LintService([_AlwaysClean()])
    assert isinstance(svc.rules, tuple)


def test_report_from_issues_counts_correctly():
    issues = [
        LintIssue(rule="a", severity=Severity.ERROR, entity_type="reco",
                  entity_id="1", field=None, message="m"),
        LintIssue(rule="a", severity=Severity.WARNING, entity_type="reco",
                  entity_id="2", field=None, message="m"),
        LintIssue(rule="b", severity=Severity.ERROR, entity_type="reco",
                  entity_id="3", field=None, message="m"),
    ]
    report = LintReport.from_issues(issues)
    assert report.n_total == 3
    assert report.n_errors == 2
    assert report.n_warnings == 1
    # #14 : clé normalisée en Severity
    assert dict(report.n_by_rule) == {"a": 2, "b": 1}
    assert all(isinstance(k, Severity) for k in report.n_by_severity)


def test_report_mappings_are_read_only_mapping_proxy():
    """L5 : `n_by_severity`/`n_by_rule` exposés en MappingProxyType."""
    issues = [
        LintIssue(rule="a", severity=Severity.ERROR, entity_type="reco",
                  entity_id="1", field=None, message="m"),
    ]
    report = LintReport.from_issues(issues)
    with pytest.raises(TypeError):
        report.n_by_severity[Severity.INFO] = 5  # type: ignore[index]
    with pytest.raises(TypeError):
        report.n_by_rule["zzz"] = 5  # type: ignore[index]


def test_report_filter_by_severity_preserves_unfiltered_counters():
    """H9 : le filter ne ment pas sur le nombre d'errors RÉEL."""
    issues = [
        LintIssue(rule="a", severity=Severity.ERROR, entity_type="reco",
                  entity_id="1", field=None, message="m"),
        LintIssue(rule="a", severity=Severity.WARNING, entity_type="reco",
                  entity_id="2", field=None, message="m"),
    ]
    report = LintReport.from_issues(issues)
    only_err = report.filter(severity=Severity.ERROR)
    assert only_err.n_total == 1
    # n_errors_unfiltered = n_errors d'origine
    assert only_err.n_errors_unfiltered == 1
    only_warn = report.filter(severity=Severity.WARNING)
    assert only_warn.n_errors_unfiltered == 1  # toujours présent


def test_report_filter_by_rule():
    issues = [
        LintIssue(rule="a", severity=Severity.ERROR, entity_type="reco",
                  entity_id="1", field=None, message="m"),
        LintIssue(rule="b", severity=Severity.ERROR, entity_type="reco",
                  entity_id="2", field=None, message="m"),
    ]
    report = LintReport.from_issues(issues)
    only_a = report.filter(rule="a")
    assert only_a.n_total == 1
    assert only_a.issues[0].rule == "a"


def test_report_filter_combined():
    issues = [
        LintIssue(rule="a", severity=Severity.ERROR, entity_type="reco",
                  entity_id="1", field=None, message="m"),
        LintIssue(rule="a", severity=Severity.WARNING, entity_type="reco",
                  entity_id="2", field=None, message="m"),
        LintIssue(rule="b", severity=Severity.ERROR, entity_type="reco",
                  entity_id="3", field=None, message="m"),
    ]
    report = LintReport.from_issues(issues)
    filt = report.filter(rule="a", severity=Severity.ERROR)
    assert filt.n_total == 1


def test_report_filter_no_args_returns_full_copy():
    issues = [
        LintIssue(rule="a", severity=Severity.ERROR, entity_type="reco",
                  entity_id="1", field=None, message="m"),
    ]
    report = LintReport.from_issues(issues)
    same = report.filter()
    assert same.n_total == 1


def test_empty_report():
    report = LintReport.from_issues([])
    assert report.n_total == 0
    assert report.n_errors == 0
    assert dict(report.n_by_severity) == {}


def test_report_no_more_as_markdown_method():
    """#8 : `as_markdown` supprimé — passer par le registry des reporters."""
    report = LintReport.from_issues([])
    assert not hasattr(report, "as_markdown")
