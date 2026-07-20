"""Tests étendus du harness : optimal assignment, per_episode, multi-source,
EvalConfig injection, JSONL log."""
from __future__ import annotations

import json
import logging

import pytest

from tools.eval.golden_set import ExpectedReco, GoldenEpisode, GoldenSet
from tools.eval.harness import DictExtractionSource, EvalHarness
from tools.eval.types import EvalConfig, EvalMetrics, ExtractedReco


def _gs(*recos: ExpectedReco, guid: str = "ep") -> GoldenSet:
    return GoldenSet(episodes=(GoldenEpisode(guid, "src", recos),))


class TestOptimalAssignment:
    def test_greedy_would_misassign(self) -> None:
        """Vérifie que l'assignment Hungarian bat le greedy.

        Si on a expected=["Matrix", "Matrix Reloaded"] et
        extracted=["Matrix Reloaded", "Matrix"], le greedy match titre 1
        à 0 mais avec un score qui consomme la mauvaise paire. Le
        Hungarian doit produire 2 matches exacts.
        """
        gs = _gs(
            ExpectedReco(title="The Matrix"),
            ExpectedReco(title="The Matrix Reloaded"),
        )
        h = EvalHarness(gs)
        r = h.evaluate([
            {"title": "The Matrix Reloaded"},
            {"title": "The Matrix"},
        ])
        # Les 2 doivent matcher exactement.
        assert r.n_exact_match + r.n_fuzzy_match == 2
        assert r.n_missed == 0
        assert r.n_spurious == 0


class TestConfigInjection:
    def test_config_overrides_threshold(self) -> None:
        gs = _gs(ExpectedReco(title="Inception"))
        cfg = EvalConfig(fuzzy_threshold=0.99)
        h = EvalHarness(gs, config=cfg)
        r = h.evaluate([{"title": "Inceptoin"}])
        assert r.n_missed == 1

    def test_config_and_threshold_conflict_raises(self) -> None:
        with pytest.raises(ValueError):
            EvalHarness(GoldenSet(), fuzzy_threshold=0.9,
                        config=EvalConfig())

    def test_extracted_reco_input_accepted(self) -> None:
        gs = _gs(ExpectedReco(title="Drive"))
        h = EvalHarness(gs)
        r = h.evaluate([ExtractedReco(title="Drive")])
        assert r.n_exact_match == 1


class TestEvaluateFull:
    def test_per_episode_aggregation(self) -> None:
        ep_a = GoldenEpisode("a", "s",
                             (ExpectedReco(title="Drive"),))
        ep_b = GoldenEpisode("b", "s",
                             (ExpectedReco(title="Inception"),))
        gs = GoldenSet(episodes=(ep_a, ep_b))
        h = EvalHarness(gs)
        src = DictExtractionSource(by_guid={
            "a": (ExtractedReco(title="Drive"),),
            "b": (ExtractedReco(title="Inception"),),
        })
        metrics = h.evaluate_full(src)
        assert isinstance(metrics, EvalMetrics)
        assert set(metrics.per_episode.keys()) == {"a", "b"}
        assert metrics.per_episode["a"].n_exact_match == 1
        assert metrics.per_episode["b"].n_exact_match == 1
        assert metrics.f1 == 1.0


class TestMultiSourceFilter:
    def test_by_source_filter(self) -> None:
        ep_a = GoldenEpisode("a", "src1", (ExpectedReco(title="X"),))
        ep_b = GoldenEpisode("b", "src2", (ExpectedReco(title="Y"),))
        gs = GoldenSet(episodes=(ep_a, ep_b))
        only_src1 = gs.by_source("src1")
        assert len(only_src1) == 1
        assert only_src1.episodes[0].source_id == "src1"


class TestJsonlLog:
    def test_emit_jsonl_logs_event(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        gs = _gs(ExpectedReco(title="Drive"))
        h = EvalHarness(gs, emit_jsonl=True)
        with caplog.at_level(logging.INFO, logger="reco"):
            h.evaluate([{"title": "Drive"}])
        # Au moins un log au format JSON.
        json_logs = [r for r in caplog.records
                     if r.message.startswith("{")]
        assert json_logs
        payload = json.loads(json_logs[0].message)
        assert payload["event"] == "eval.compare"


class TestDictExtractionSource:
    def test_from_legacy_dict(self) -> None:
        src = DictExtractionSource.from_legacy_dict({
            "ep1": [{"title": "A"}],
            "ep2": "ignored",  # non-list ignorée
        })
        assert tuple(src.episode_guids()) == ("ep1",)

    def test_from_legacy_list_with_guid(self) -> None:
        src = DictExtractionSource.from_legacy_dict(
            [{"title": "A"}], default_guid="ep1",
        )
        assert tuple(src.for_episode("ep1"))[0].title == "A"

    def test_blank_title_skipped(self) -> None:
        with pytest.raises(ValueError):
            DictExtractionSource.from_legacy_dict({"ep1": [{"title": ""}]})
