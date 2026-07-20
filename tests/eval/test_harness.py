"""Tests du harness d'évaluation."""
from __future__ import annotations

import pytest

from tools.eval.golden_set import ExpectedReco, GoldenEpisode, GoldenSet
from tools.eval.harness import EvalHarness, _parse_timestamp_to_seconds
from tools.eval.metrics import MatchVerdict


def _gs_with(*recos: ExpectedReco, guid: str = "ep") -> GoldenSet:
    return GoldenSet(episodes=(GoldenEpisode(guid, "src", recos),))


class TestParseTimestamp:
    def test_hms(self) -> None:
        assert _parse_timestamp_to_seconds("01:02:03") == 3723

    def test_ms(self) -> None:
        assert _parse_timestamp_to_seconds("02:03") == 123

    def test_s(self) -> None:
        assert _parse_timestamp_to_seconds("45") == 45

    def test_none(self) -> None:
        assert _parse_timestamp_to_seconds(None) is None

    def test_invalid_chars(self) -> None:
        assert _parse_timestamp_to_seconds("abc") is None

    def test_too_many_parts(self) -> None:
        assert _parse_timestamp_to_seconds("1:2:3:4") is None


class TestHarnessInit:
    def test_default_threshold(self) -> None:
        h = EvalHarness(GoldenSet())
        assert h._fuzzy_threshold == 0.85

    def test_custom_threshold(self) -> None:
        h = EvalHarness(GoldenSet(), fuzzy_threshold=0.9)
        assert h._fuzzy_threshold == 0.9

    def test_invalid_threshold_zero(self) -> None:
        with pytest.raises(ValueError):
            EvalHarness(GoldenSet(), fuzzy_threshold=0.0)

    def test_invalid_threshold_above_one(self) -> None:
        with pytest.raises(ValueError):
            EvalHarness(GoldenSet(), fuzzy_threshold=1.5)


class TestEvaluate:
    def test_perfect_extraction(self) -> None:
        gs = _gs_with(
            ExpectedReco(title="Drive", creator="Refn"),
            ExpectedReco(title="Inception", creator="Nolan"),
        )
        h = EvalHarness(gs)
        result = h.evaluate([
            {"title": "Drive", "creator": "Refn"},
            {"title": "Inception", "creator": "Nolan"},
        ])
        assert result.n_exact_match == 2
        assert result.n_missed == 0
        assert result.n_spurious == 0
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0

    def test_perfect_score_1_0(self) -> None:
        gs = _gs_with(ExpectedReco(title="Drive"))
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive"}])
        assert r.f1 == 1.0

    def test_zero_score_no_overlap(self) -> None:
        gs = _gs_with(ExpectedReco(title="Drive"))
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Completely Different Title XYZ"}])
        assert r.n_missed == 1
        assert r.n_spurious == 1
        assert r.precision == 0.0
        assert r.recall == 0.0
        assert r.f1 == 0.0

    def test_missed_reco_counted_correctly(self) -> None:
        gs = _gs_with(
            ExpectedReco(title="Drive"),
            ExpectedReco(title="Inception"),
        )
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive"}])
        assert r.n_exact_match == 1
        assert r.n_missed == 1
        assert r.recall == pytest.approx(0.5)
        assert r.precision == 1.0

    def test_spurious_reco_counted_correctly(self) -> None:
        gs = _gs_with(ExpectedReco(title="Drive"))
        h = EvalHarness(gs)
        r = h.evaluate([
            {"title": "Drive"},
            {"title": "Spurious One"},
            {"title": "Spurious Two"},
        ])
        assert r.n_exact_match == 1
        assert r.n_spurious == 2
        assert r.precision == pytest.approx(1.0 / 3.0)
        assert r.recall == 1.0

    def test_fuzzy_match_within_threshold(self) -> None:
        gs = _gs_with(ExpectedReco(title="Inception"))
        h = EvalHarness(gs, fuzzy_threshold=0.85)
        r = h.evaluate([{"title": "Inceptoin"}])  # typo
        assert r.n_fuzzy_match == 1
        assert r.n_exact_match == 0
        assert r.precision == 1.0
        assert r.recall == 1.0

    def test_below_threshold_is_missed(self) -> None:
        gs = _gs_with(ExpectedReco(title="Inception"))
        h = EvalHarness(gs, fuzzy_threshold=0.99)
        r = h.evaluate([{"title": "Inceptoin"}])
        assert r.n_missed == 1
        assert r.n_spurious == 1

    def test_wrong_timestamp_classified(self) -> None:
        gs = _gs_with(
            ExpectedReco(
                title="Drive", timestamp="00:34:00", timestamp_tolerance_sec=30,
            ),
        )
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive", "timestamp": "00:40:00"}])
        assert r.n_wrong_timestamp == 1
        assert r.n_exact_match == 0
        # WRONG_TIMESTAMP n'est pas un TP
        assert r.precision == 0.0
        assert r.recall == 0.0

    def test_timestamp_within_tolerance_passes(self) -> None:
        gs = _gs_with(
            ExpectedReco(
                title="Drive", timestamp="00:34:00", timestamp_tolerance_sec=30,
            ),
        )
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive", "timestamp": "00:34:20"}])
        assert r.n_exact_match == 1
        assert r.n_wrong_timestamp == 0

    def test_no_extracted_timestamp_is_tolerant(self) -> None:
        gs = _gs_with(ExpectedReco(title="Drive", timestamp="00:34:00"))
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive"}])
        assert r.n_exact_match == 1
        assert r.n_wrong_timestamp == 0

    def test_invalid_expected_timestamp_is_tolerant(self) -> None:
        gs = _gs_with(ExpectedReco(title="Drive", timestamp="invalid"))
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive", "timestamp": "00:00:00"}])
        assert r.n_exact_match == 1

    def test_invalid_extracted_timestamp_is_tolerant(self) -> None:
        gs = _gs_with(ExpectedReco(title="Drive", timestamp="00:34:00"))
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive", "timestamp": "garbage"}])
        assert r.n_exact_match == 1

    def test_precision_recall_f1_formula(self) -> None:
        # 4 attendus, 5 extraits, 3 matchs → P=3/5, R=3/4, F1 = 2*P*R/(P+R)
        gs = _gs_with(
            ExpectedReco(title="A"),
            ExpectedReco(title="B"),
            ExpectedReco(title="C"),
            ExpectedReco(title="D"),
        )
        h = EvalHarness(gs)
        r = h.evaluate([
            {"title": "A"}, {"title": "B"}, {"title": "C"},
            {"title": "Z1"}, {"title": "Z2"},
        ])
        assert r.precision == pytest.approx(3 / 5)
        assert r.recall == pytest.approx(3 / 4)
        expected_f1 = 2 * (3 / 5) * (3 / 4) / ((3 / 5) + (3 / 4))
        assert r.f1 == pytest.approx(expected_f1)

    def test_evaluate_specific_episode(self) -> None:
        ep_a = GoldenEpisode("a", "s", (ExpectedReco(title="Drive"),))
        ep_b = GoldenEpisode("b", "s", (ExpectedReco(title="Inception"),))
        gs = GoldenSet(episodes=(ep_a, ep_b))
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive"}], episode_guid="a")
        assert r.n_exact_match == 1
        assert r.n_expected == 1

    def test_evaluate_unknown_episode_raises(self) -> None:
        gs = _gs_with(ExpectedReco(title="X"))
        h = EvalHarness(gs)
        with pytest.raises(KeyError):
            h.evaluate([], episode_guid="ghost")

    def test_evaluate_empty_extracted(self) -> None:
        gs = _gs_with(ExpectedReco(title="Drive"))
        h = EvalHarness(gs)
        r = h.evaluate([])
        assert r.n_missed == 1
        assert r.n_spurious == 0
        assert r.precision == 0.0
        assert r.recall == 0.0

    def test_details_record_verdict_per_reco(self) -> None:
        gs = _gs_with(ExpectedReco(title="Drive"))
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive"}, {"title": "Extra"}])
        verdicts = [d["verdict"] for d in r.details]
        assert MatchVerdict.EXACT_MATCH.value in verdicts
        assert MatchVerdict.SPURIOUS.value in verdicts

    def test_one_extracted_matches_only_best_expected(self) -> None:
        # Une extraction ne doit pas matcher 2 expected — la 2e doit être missed.
        gs = _gs_with(
            ExpectedReco(title="Drive"),
            ExpectedReco(title="Drive"),
        )
        h = EvalHarness(gs)
        r = h.evaluate([{"title": "Drive"}])
        assert r.n_exact_match == 1
        assert r.n_missed == 1
