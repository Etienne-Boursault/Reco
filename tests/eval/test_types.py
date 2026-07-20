"""Tests des dataclasses & Protocols ``tools.eval.types``."""
from __future__ import annotations

import json
from types import MappingProxyType

import pytest

from tools.eval.types import (
    DEFAULT_FUZZY_THRESHOLD,
    EvalConfig,
    EvalDetail,
    EvalMetrics,
    ExtractedReco,
    ReportFormat,
    RunManifest,
)


class TestExtractedReco:
    def test_minimal(self) -> None:
        r = ExtractedReco.from_dict({"title": "Drive"})
        assert r.title == "Drive"
        assert r.creator is None
        assert r.timestamp is None

    def test_full(self) -> None:
        r = ExtractedReco.from_dict(
            {"title": "Drive", "creator": "Refn", "timestamp": "00:12:00",
             "extra_field": "x"},
        )
        assert r.creator == "Refn"
        assert r.timestamp == "00:12:00"
        assert r.extra["extra_field"] == "x"

    def test_blank_title_raises(self) -> None:
        with pytest.raises(ValueError, match="title"):
            ExtractedReco.from_dict({"title": "   "})

    def test_immutable(self) -> None:
        r = ExtractedReco(title="X")
        with pytest.raises(AttributeError):
            r.title = "Y"  # type: ignore[misc]

    def test_extra_is_mappingproxy(self) -> None:
        r = ExtractedReco.from_dict({"title": "X", "k": "v"})
        assert isinstance(r.extra, MappingProxyType)


class TestEvalConfig:
    def test_defaults(self) -> None:
        c = EvalConfig()
        assert c.fuzzy_threshold == DEFAULT_FUZZY_THRESHOLD
        assert c.timestamp_tolerance_sec == 5

    def test_invalid_threshold(self) -> None:
        with pytest.raises(ValueError):
            EvalConfig(fuzzy_threshold=0.0)
        with pytest.raises(ValueError):
            EvalConfig(fuzzy_threshold=1.5)

    def test_invalid_tolerance(self) -> None:
        with pytest.raises(ValueError):
            EvalConfig(timestamp_tolerance_sec=-1)

    def test_from_dict(self) -> None:
        c = EvalConfig.from_dict({"fuzzy_threshold": 0.9})
        assert c.fuzzy_threshold == 0.9

    def test_from_dict_ignores_unknown(self) -> None:
        c = EvalConfig.from_dict({"fuzzy_threshold": 0.9, "garbage": 42})
        assert c.fuzzy_threshold == 0.9


class TestEvalDetail:
    def test_minimal(self) -> None:
        d = EvalDetail(verdict="missed", expected_title="X")
        assert d.to_dict() == {"verdict": "missed", "expected_title": "X"}

    def test_full_round_trip(self) -> None:
        d = EvalDetail(verdict="exact", expected_title="X",
                       matched_title="X", score=1.0, episode_guid="ep1")
        out = d.to_dict()
        assert out["score"] == 1.0
        assert out["episode_guid"] == "ep1"

    def test_immutable(self) -> None:
        d = EvalDetail(verdict="exact")
        with pytest.raises(AttributeError):
            d.verdict = "missed"  # type: ignore[misc]


class TestEvalMetrics:
    def test_per_episode_wrapped(self) -> None:
        inner = EvalMetrics(
            n_expected=1, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
            n_missed=0, n_spurious=0, n_wrong_timestamp=0,
            precision=1.0, recall=1.0, f1=1.0,
        )
        outer = EvalMetrics(
            n_expected=1, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
            n_missed=0, n_spurious=0, n_wrong_timestamp=0,
            precision=1.0, recall=1.0, f1=1.0,
            per_episode={"ep": inner},
        )
        assert isinstance(outer.per_episode, MappingProxyType)
        assert outer.per_episode["ep"] is inner

    def test_to_summary_dict(self) -> None:
        m = EvalMetrics(
            n_expected=2, n_extracted=1, n_exact_match=1, n_fuzzy_match=0,
            n_missed=1, n_spurious=0, n_wrong_timestamp=0,
            precision=1.0, recall=0.5, f1=2 / 3,
        )
        d = m.to_summary_dict()
        assert d["recall"] == 0.5
        assert d["n_missed"] == 1


class TestRunManifest:
    def test_round_trip(self) -> None:
        m = RunManifest(
            run_id="r1", timestamp="2026-06-10T00:00:00+00:00",
            git_sha="abc", config_hash="x", golden_set_hash="y",
            scores={"f1": 0.9}, sources=("un-bon-moment",),
        )
        d = m.to_dict()
        again = RunManifest.from_dict(d)
        assert again == m

    def test_to_json_is_valid(self) -> None:
        m = RunManifest(
            run_id="r1", timestamp="2026-06-10T00:00:00+00:00",
            git_sha="", config_hash="", golden_set_hash="",
        )
        parsed = json.loads(m.to_json())
        assert parsed["run_id"] == "r1"


class TestReportFormat:
    def test_values(self) -> None:
        assert ReportFormat.CSV == "csv"
        assert ReportFormat.MARKDOWN == "markdown"
        assert set(ReportFormat) == {"csv", "markdown"}
