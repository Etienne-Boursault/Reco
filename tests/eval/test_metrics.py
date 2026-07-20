"""Tests des fonctions métriques precision/recall/F1."""
from __future__ import annotations

import pytest

from tools.eval.metrics import EvalResult, MatchVerdict, f1, precision, recall


class TestPrecision:
    def test_perfect(self) -> None:
        assert precision(5, 5) == 1.0

    def test_half(self) -> None:
        assert precision(2, 4) == 0.5

    def test_zero_extracted(self) -> None:
        assert precision(0, 0) == 0.0

    def test_negative_extracted(self) -> None:
        assert precision(0, -1) == 0.0


class TestRecall:
    def test_perfect(self) -> None:
        assert recall(5, 5) == 1.0

    def test_half(self) -> None:
        assert recall(1, 2) == 0.5

    def test_zero_expected(self) -> None:
        assert recall(0, 0) == 0.0


class TestF1:
    def test_perfect(self) -> None:
        assert f1(1.0, 1.0) == 1.0

    def test_zero_precision(self) -> None:
        assert f1(0.0, 1.0) == 0.0

    def test_zero_recall(self) -> None:
        assert f1(1.0, 0.0) == 0.0

    def test_balanced(self) -> None:
        # F1(0.5, 0.5) = 0.5
        assert f1(0.5, 0.5) == pytest.approx(0.5)

    def test_unbalanced(self) -> None:
        # F1(1.0, 0.5) = 2/3
        assert f1(1.0, 0.5) == pytest.approx(2.0 / 3.0)


class TestMatchVerdict:
    def test_string_values(self) -> None:
        assert MatchVerdict.EXACT_MATCH == "exact"
        assert MatchVerdict.FUZZY_MATCH == "fuzzy"
        assert MatchVerdict.MISSED == "missed"
        assert MatchVerdict.SPURIOUS == "spurious"
        assert MatchVerdict.WRONG_TIMESTAMP == "wrong_ts"


class TestEvalResult:
    def test_default_details_empty(self) -> None:
        r = EvalResult(
            n_expected=1, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
            n_missed=0, n_spurious=0, n_wrong_timestamp=0,
            precision=1.0, recall=1.0, f1=1.0,
        )
        assert r.details == ()
