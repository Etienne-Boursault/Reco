"""Tests des reporters CSV et Markdown."""
from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from tools.eval.metrics import EvalResult, MatchVerdict
from tools.eval.reporters.csv_reporter import render_csv, write_csv
from tools.eval.reporters.markdown_reporter import render_markdown, write_markdown


@pytest.fixture
def sample_result() -> EvalResult:
    return EvalResult(
        n_expected=3,
        n_extracted=3,
        n_exact_match=2,
        n_fuzzy_match=1,
        n_missed=0,
        n_spurious=0,
        n_wrong_timestamp=0,
        precision=1.0,
        recall=1.0,
        f1=1.0,
        details=(
            {
                "expected_title": "Drive",
                "matched_title": "Drive",
                "verdict": MatchVerdict.EXACT_MATCH.value,
                "score": 1.0,
            },
            {
                "expected_title": "Inception",
                "matched_title": "Inceptoin",
                "verdict": MatchVerdict.FUZZY_MATCH.value,
                "score": 0.92,
            },
            {
                "expected_title": "1984",
                "matched_title": "1984",
                "verdict": MatchVerdict.EXACT_MATCH.value,
                "score": 1.0,
            },
        ),
    )


class TestCsvReporter:
    def test_render_contains_summary(self, sample_result: EvalResult) -> None:
        out = render_csv(sample_result)
        assert "# summary" in out
        assert "precision" in out
        assert "# details" in out

    def test_render_parsable(self, sample_result: EvalResult) -> None:
        out = render_csv(sample_result)
        rows = list(csv.reader(io.StringIO(out)))
        # Au moins la ligne summary header + summary values + details header
        assert any("precision" in r for r in rows if r)

    def test_write_creates_file(
        self, sample_result: EvalResult, tmp_path: Path,
    ) -> None:
        p = tmp_path / "sub" / "out.csv"
        written = write_csv(sample_result, p)
        assert written == p
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        assert "Drive" in content

    def test_render_with_spurious(self) -> None:
        r = EvalResult(
            n_expected=1, n_extracted=2, n_exact_match=1, n_fuzzy_match=0,
            n_missed=0, n_spurious=1, n_wrong_timestamp=0,
            precision=0.5, recall=1.0, f1=2 / 3,
            details=(
                {
                    "expected_title": "Drive", "matched_title": "Drive",
                    "verdict": "exact", "score": 1.0,
                },
                {"extracted_title": "Extra", "verdict": "spurious"},
            ),
        )
        out = render_csv(r)
        assert "Extra" in out


class TestMarkdownReporter:
    def test_render_contains_metrics(self, sample_result: EvalResult) -> None:
        out = render_markdown(sample_result)
        assert "# Eval report" in out
        assert "Precision" in out
        assert "Recall" in out
        assert "F1" in out

    def test_render_contains_details(self, sample_result: EvalResult) -> None:
        out = render_markdown(sample_result)
        assert "Drive" in out
        assert "Inceptoin" in out

    def test_custom_title(self, sample_result: EvalResult) -> None:
        out = render_markdown(sample_result, title="Run 2026-06-10 — Haiku")
        assert "Run 2026-06-10 — Haiku" in out

    def test_write_creates_file(
        self, sample_result: EvalResult, tmp_path: Path,
    ) -> None:
        p = tmp_path / "sub" / "out.md"
        written = write_markdown(sample_result, p, title="X")
        assert written == p
        assert p.exists()
        assert "X" in p.read_text(encoding="utf-8")

    def test_render_handles_non_float_score(self) -> None:
        r = EvalResult(
            n_expected=1, n_extracted=0, n_exact_match=0, n_fuzzy_match=0,
            n_missed=1, n_spurious=0, n_wrong_timestamp=0,
            precision=0.0, recall=0.0, f1=0.0,
            details=(
                {"expected_title": "X", "verdict": "missed", "score": ""},
            ),
        )
        out = render_markdown(r)
        assert "missed" in out

    def test_render_handles_spurious_extracted_title(self) -> None:
        r = EvalResult(
            n_expected=0, n_extracted=1, n_exact_match=0, n_fuzzy_match=0,
            n_missed=0, n_spurious=1, n_wrong_timestamp=0,
            precision=0.0, recall=0.0, f1=0.0,
            details=({"extracted_title": "Ghost", "verdict": "spurious"},),
        )
        out = render_markdown(r)
        assert "Ghost" in out


class TestReportersPackage:
    def test_public_api(self) -> None:
        from tools.eval import reporters
        # API exposée
        assert hasattr(reporters, "render_csv")
        assert hasattr(reporters, "render_markdown")
        assert hasattr(reporters, "write_csv")
        assert hasattr(reporters, "write_markdown")
