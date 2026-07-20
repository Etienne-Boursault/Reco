"""Tests : chargement et validation du golden set."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.eval.golden_set import (
    ExpectedReco,
    GoldenEpisode,
    GoldenSet,
    GoldenSetError,
    load_golden_set,
)


GOLDEN_FIXTURES = Path(__file__).parent / "golden_set"


class TestExpectedReco:
    def test_minimal_dict(self) -> None:
        r = ExpectedReco.from_dict({"title": "Drive"})
        assert r.title == "Drive"
        assert r.creator is None
        assert r.types == ()
        assert r.must_have is True
        assert r.timestamp_tolerance_sec == 30
        assert r.kind == "reco"
        assert r.notes == ""

    def test_full_dict(self) -> None:
        r = ExpectedReco.from_dict({
            "title": "Drive",
            "creator": "Refn",
            "types": ["film"],
            "timestamp": "00:34:12",
            "timestamp_tolerance_sec": 60,
            "recommended_by": "Navo",
            "kind": "reco",
            "must_have": False,
            "notes": "abc",
        })
        assert r.creator == "Refn"
        assert r.types == ("film",)
        assert r.timestamp == "00:34:12"
        assert r.timestamp_tolerance_sec == 60
        assert r.recommended_by == "Navo"
        assert r.must_have is False
        assert r.notes == "abc"

    def test_missing_title_raises(self) -> None:
        with pytest.raises(GoldenSetError, match="title"):
            ExpectedReco.from_dict({})

    def test_blank_title_raises(self) -> None:
        with pytest.raises(GoldenSetError):
            ExpectedReco.from_dict({"title": "   "})

    def test_types_not_list_raises(self) -> None:
        with pytest.raises(GoldenSetError, match="types"):
            ExpectedReco.from_dict({"title": "Drive", "types": "film"})


class TestGoldenEpisode:
    def test_from_dict_ok(self) -> None:
        ep = GoldenEpisode.from_dict({
            "episode_guid": "g1",
            "source_id": "src",
            "expected_recos": [{"title": "A"}, {"title": "B"}],
        })
        assert ep.episode_guid == "g1"
        assert ep.source_id == "src"
        assert len(ep.expected_recos) == 2

    def test_missing_guid_raises(self) -> None:
        with pytest.raises(GoldenSetError):
            GoldenEpisode.from_dict({"source_id": "s", "expected_recos": []})

    def test_missing_source_raises(self) -> None:
        with pytest.raises(GoldenSetError):
            GoldenEpisode.from_dict({"episode_guid": "g", "expected_recos": []})

    def test_recos_not_list_raises(self) -> None:
        with pytest.raises(GoldenSetError, match="expected_recos"):
            GoldenEpisode.from_dict({
                "episode_guid": "g", "source_id": "s", "expected_recos": "nope",
            })


class TestGoldenSet:
    def test_iter_and_len(self) -> None:
        gs = GoldenSet(episodes=(
            GoldenEpisode("g1", "s", ()),
            GoldenEpisode("g2", "s", ()),
        ))
        assert len(gs) == 2
        assert [e.episode_guid for e in gs] == ["g1", "g2"]

    def test_by_guid_found(self) -> None:
        ep = GoldenEpisode("g1", "s", ())
        gs = GoldenSet(episodes=(ep,))
        assert gs.by_guid("g1") is ep

    def test_by_guid_missing(self) -> None:
        gs = GoldenSet(episodes=())
        assert gs.by_guid("unknown") is None


class TestLoadGoldenSet:
    def test_load_directory(self) -> None:
        gs = load_golden_set(GOLDEN_FIXTURES)
        assert len(gs) == 3
        guids = {e.episode_guid for e in gs}
        assert guids == {"ep001", "ep002", "ep003"}

    def test_load_single_file(self) -> None:
        gs = load_golden_set(GOLDEN_FIXTURES / "ep001.json")
        assert len(gs) == 1
        assert gs.episodes[0].episode_guid == "ep001"
        assert len(gs.episodes[0].expected_recos) == 5

    def test_load_missing_path(self, tmp_path: Path) -> None:
        with pytest.raises(GoldenSetError, match="introuvable"):
            load_golden_set(tmp_path / "ghost")

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        with pytest.raises(GoldenSetError, match="lire"):
            load_golden_set(bad)

    def test_load_invalid_schema(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        with pytest.raises(GoldenSetError):
            load_golden_set(bad)
