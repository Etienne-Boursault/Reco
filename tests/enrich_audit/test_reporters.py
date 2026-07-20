"""Tests : tools.enrich_audit.reporters — markdown / json / jsonl."""
from __future__ import annotations

import json
from pathlib import Path

from enrich_audit.reporters import format_json, format_markdown, write_jsonl_log
from enrich_audit.reporters.markdown_reporter import _md_escape
from enrich_audit.service import AuditResult, SourceAuditReport
from enrich_audit.types import Severity, Suspicion


def _report_with_one_suspect() -> SourceAuditReport:
    return SourceAuditReport(
        source_id="ubm",
        results=(
            AuditResult(
                item_id="bad",
                is_suspect=True,
                suspicions=(
                    Suspicion(kind="title_mismatch", detail="X != Y",
                              severity=Severity.WARNING, confidence=0.8),
                ),
            ),
            AuditResult(item_id="ok", is_suspect=False, suspicions=()),
        ),
        skipped_no_tmdb=3,
        skipped_no_cache=1,
        skipped_check_error=2,
    )


# ===== format_markdown =====================================================


def test_format_markdown_lists_suspects():
    text = format_markdown(_report_with_one_suspect())
    assert "Audit TMDB" in text
    assert "ubm" in text
    assert "bad" in text
    # ADR 0019 S-03 : escape_md union — `_` est désormais échappé en `\_`.
    assert "title\\_mismatch" in text
    assert "X != Y" in text
    assert "ok" not in text.split("## Items suspects")[1]
    assert "Skipped (sans tmdb) : 3" in text
    assert "Skipped (sans cache) : 1" in text
    assert "Check errors : 2" in text


def test_format_markdown_includes_cache_version_mismatch_count():
    rep = SourceAuditReport(
        source_id="ubm",
        results=(AuditResult(item_id="ok", is_suspect=False, suspicions=()),),
        skipped_cache_version_mismatch=5,
    )
    text = format_markdown(rep)
    assert "cache version mismatch" in text
    assert "5" in text


def test_format_markdown_no_suspect():
    rep = SourceAuditReport(source_id="ubm", results=(
        AuditResult(item_id="ok", is_suspect=False, suspicions=()),
    ))
    text = format_markdown(rep)
    assert "Aucun item suspect" in text
    assert "## Items suspects" not in text


def test_format_markdown_includes_severity_label():
    text = format_markdown(_report_with_one_suspect())
    assert "WARNING" in text


def test_format_markdown_results_sorted_by_id():
    """CR senior L4 : tri stable."""
    rep = SourceAuditReport(
        source_id="ubm",
        results=(
            AuditResult(item_id="zzz", is_suspect=True,
                        suspicions=(Suspicion(kind="k", detail="d"),)),
            AuditResult(item_id="aaa", is_suspect=True,
                        suspicions=(Suspicion(kind="k", detail="d"),)),
        ),
    )
    text = format_markdown(rep)
    idx_aaa = text.index("aaa")
    idx_zzz = text.index("zzz")
    assert idx_aaa < idx_zzz


def test_format_markdown_escapes_pipe_in_id():
    """CR senior M5 : pipe `|` doit être échappé dans l'item_id."""
    # On ne peut pas avoir un `|` dans un AuditResult.item_id (validation
    # interne refuse). On vérifie l'escape directement.
    assert _md_escape("a|b") == "a\\|b"


def test_format_markdown_escapes_backticks_in_detail():
    assert _md_escape("a`b") == "a\\`b"


def test_format_markdown_escapes_newlines_in_detail():
    assert _md_escape("a\nb") == "a b"


def test_format_markdown_escapes_backslash():
    assert _md_escape("a\\b") == "a\\\\b"


def test_format_markdown_in_full_report_uses_escape():
    """Round-trip : un détail multi-ligne devient un détail single-line."""
    rep = SourceAuditReport(
        source_id="src",
        results=(
            AuditResult(
                item_id="bad",
                is_suspect=True,
                suspicions=(Suspicion(kind="x", detail="line1\nline2"),),
            ),
        ),
    )
    text = format_markdown(rep)
    # La détail "line1\nline2" doit apparaître transformée en "line1 line2".
    suspect_section = text.split("## Items suspects")[1]
    assert "line1 line2" in suspect_section


# ===== format_json =========================================================


def test_format_json_is_valid_and_complete():
    rep = _report_with_one_suspect()
    raw = json.loads(format_json(rep))
    assert raw["sourceId"] == "ubm"
    assert raw["audited"] == 2
    assert raw["suspect"] == 1
    assert raw["clean"] == 1
    assert raw["skippedNoTmdb"] == 3
    assert raw["skippedNoCache"] == 1
    assert raw["skippedCheckError"] == 2
    assert len(raw["results"]) == 2
    bad = next(r for r in raw["results"] if r["itemId"] == "bad")
    assert bad["enrichmentSuspect"] is True
    assert bad["suspicions"][0]["kind"] == "title_mismatch"
    assert bad["suspicions"][0]["severity"] == "warning"
    assert bad["suspicions"][0]["confidence"] == 0.8


def test_format_json_results_sorted():
    rep = SourceAuditReport(
        source_id="src",
        results=(
            AuditResult(item_id="zzz", is_suspect=False, suspicions=()),
            AuditResult(item_id="aaa", is_suspect=False, suspicions=()),
        ),
    )
    raw = json.loads(format_json(rep))
    assert [r["itemId"] for r in raw["results"]] == ["aaa", "zzz"]


# ===== write_jsonl_log =====================================================


def test_jsonl_log_appends_one_line_per_suspect(tmp_path: Path):
    log_path = tmp_path / "logs" / "audit.jsonl"
    rep = _report_with_one_suspect()
    n = write_jsonl_log(rep, log_path=log_path, timestamp="2026-06-10T12:00:00Z")
    assert n == 1
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["source"] == "ubm"
    assert parsed["itemId"] == "bad"
    assert parsed["kinds"] == ["title_mismatch"]
    assert parsed["severities"] == ["warning"]
    assert parsed["ts"] == "2026-06-10T12:00:00Z"


def test_jsonl_log_no_op_when_no_suspect(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    rep = SourceAuditReport(source_id="src", results=(
        AuditResult(item_id="ok", is_suspect=False, suspicions=()),
    ))
    n = write_jsonl_log(rep, log_path=log_path)
    assert n == 0
    assert not log_path.exists()


def test_jsonl_log_appends_to_existing_file(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    log_path.write_text("previous-line\n", encoding="utf-8")
    rep = _report_with_one_suspect()
    write_jsonl_log(rep, log_path=log_path, timestamp="2026-06-10T12:00:00Z")
    content = log_path.read_text(encoding="utf-8")
    assert content.startswith("previous-line\n")


def test_jsonl_log_default_timestamp_is_iso8601(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    rep = _report_with_one_suspect()
    write_jsonl_log(rep, log_path=log_path)
    parsed = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert parsed["ts"].startswith("20") and parsed["ts"].endswith("Z")
