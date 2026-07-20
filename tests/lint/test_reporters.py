"""Tests TDD pour les reporters (markdown + json + registry)."""
from __future__ import annotations

import json

import pytest

from lint.reporters import (
    REPORTERS,
    build_summary,
    get_reporter,
    render_json,
    render_markdown,
)
from lint.reporters.json_reporter import JsonReporter
from lint.reporters.markdown_reporter import MarkdownReporter
from lint.rules.base import LintIssue, Severity
from lint.service import LintReport


def _issue(rule, sev, eid="x", field="title", message=None):
    return LintIssue(
        rule=rule, severity=sev, entity_type="reco",
        entity_id=eid, field=field,
        message=message if message is not None else f"{rule} on {eid}",
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_counts():
    report = LintReport.from_issues([
        _issue("a", Severity.ERROR, "1"),
        _issue("a", Severity.WARNING, "2"),
        _issue("b", Severity.INFO, "3"),
    ])
    s = build_summary(report)
    assert s.n_total == 3
    assert s.n_errors == 1
    assert s.n_warnings == 1
    assert s.n_infos == 1


def test_summary_top_rules_sorted_by_count_desc_then_name():
    report = LintReport.from_issues([
        _issue("c", Severity.ERROR, "1"),
        _issue("a", Severity.ERROR, "2"),
        _issue("a", Severity.ERROR, "3"),
        _issue("b", Severity.ERROR, "4"),
        _issue("b", Severity.ERROR, "5"),
    ])
    s = build_summary(report, top_n=3)
    assert s.top_rules == (("a", 2), ("b", 2), ("c", 1))


def test_summary_top_n_limits():
    report = LintReport.from_issues([
        _issue(f"r{i}", Severity.ERROR, str(i)) for i in range(10)
    ])
    s = build_summary(report, top_n=3)
    assert len(s.top_rules) == 3


# ---------------------------------------------------------------------------
# Markdown reporter
# ---------------------------------------------------------------------------


def test_markdown_contains_summary_section():
    report = LintReport.from_issues([
        _issue("required_fields", Severity.ERROR, "ubm-1"),
    ])
    md = render_markdown(report)
    assert "# Dataset Lint Report" in md
    assert "## Summary" in md
    assert "Total issues : **1**" in md
    assert "Errors       : **1**" in md


def test_markdown_groups_by_severity_and_rule():
    report = LintReport.from_issues([
        _issue("a", Severity.ERROR, "1"),
        _issue("b", Severity.WARNING, "2"),
    ])
    md = render_markdown(report)
    assert "## Errors (1)" in md
    assert "## Warnings (1)" in md
    assert "### `a` (1)" in md
    assert "### `b` (1)" in md


def test_markdown_includes_top_rules():
    report = LintReport.from_issues([
        _issue("very_violated", Severity.ERROR, "1"),
        _issue("very_violated", Severity.ERROR, "2"),
    ])
    md = render_markdown(report)
    assert "Top rules" in md
    assert "very_violated" in md


def test_markdown_empty_report_renders_summary_only():
    report = LintReport.from_issues([])
    md = render_markdown(report)
    assert "Total issues : **0**" in md
    assert "Errors (0)" not in md


def test_markdown_issue_with_no_field():
    issue = LintIssue(
        rule="r", severity=Severity.ERROR, entity_type="item",
        entity_id="abc", field=None, message="probleme",
    )
    md = render_markdown(LintReport.from_issues([issue]))
    assert "item/abc" in md
    assert "probleme" in md


def test_markdown_deterministic_sort_for_diffs():
    issues = [
        _issue("b", Severity.ERROR, "2"),
        _issue("a", Severity.ERROR, "3"),
        _issue("a", Severity.ERROR, "1"),
    ]
    r1 = LintReport.from_issues(issues)
    r2 = LintReport.from_issues(list(reversed(issues)))
    assert render_markdown(r1) == render_markdown(r2)


def test_markdown_escapes_backticks_and_asterisks_in_message():
    """M3 : injection markdown depuis le message LLM neutralisée."""
    issue = _issue(
        "r", Severity.ERROR, eid="x", field="title",
        message="bad `code` and **bold** here",
    )
    md = render_markdown(LintReport.from_issues([issue]))
    # Backslash devant chaque ` et *.
    assert "\\`code\\`" in md
    assert "\\*\\*bold\\*\\*" in md


# ---------------------------------------------------------------------------
# JSON reporter (H10 / #11)
# ---------------------------------------------------------------------------


def test_json_reporter_outputs_jsonl_with_meta_line():
    report = LintReport.from_issues([
        _issue("a", Severity.ERROR, "1"),
        _issue("b", Severity.WARNING, "2"),
    ])
    out = render_json(report)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    payloads = [json.loads(ln) for ln in lines]
    assert payloads[0]["kind"] == "meta"
    assert payloads[0]["total"] == 2
    assert payloads[0]["errors"] == 1
    assert {p["kind"] for p in payloads[1:]} == {"issue"}


def test_json_reporter_issues_include_all_fields():
    report = LintReport.from_issues([
        _issue("a", Severity.ERROR, "1"),
    ])
    payloads = [
        json.loads(ln) for ln in render_json(report).splitlines() if ln.strip()
    ]
    issue = next(p for p in payloads if p["kind"] == "issue")
    assert issue["rule"] == "a"
    assert issue["severity"] == "error"
    assert issue["entityId"] == "1"
    assert issue["field"] == "title"


def test_json_reporter_empty_report():
    report = LintReport.from_issues([])
    out = render_json(report)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 1
    meta = json.loads(lines[0])
    assert meta["total"] == 0


# ---------------------------------------------------------------------------
# Registry (P1 #7)
# ---------------------------------------------------------------------------


def test_reporter_registry_contains_markdown_and_json():
    assert "markdown" in REPORTERS
    assert "json" in REPORTERS


def test_get_reporter_markdown():
    assert isinstance(get_reporter("markdown"), MarkdownReporter)


def test_get_reporter_json():
    assert isinstance(get_reporter("json"), JsonReporter)


def test_get_reporter_unknown_raises():
    with pytest.raises(ValueError):
        get_reporter("xml")


def test_reporter_has_format_id_attr():
    assert MarkdownReporter.format_id == "markdown"
    assert JsonReporter.format_id == "json"


def test_reporter_render_via_protocol_call():
    report = LintReport.from_issues([_issue("a", Severity.ERROR, "1")])
    md = get_reporter("markdown").render(report)
    assert "Dataset Lint Report" in md
    js = get_reporter("json").render(report)
    assert json.loads(js.splitlines()[0])["kind"] == "meta"
