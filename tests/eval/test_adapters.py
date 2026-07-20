"""Tests des adaptateurs : ``LegacyRecoExtractionSource``."""
from __future__ import annotations

from dataclasses import dataclass

from tools.eval.adapters import (
    LegacyRecoExtractionSource,
    legacy_recos_to_extracted,
)
from tools.eval.types import ExtractionSource


@dataclass
class _FakeLegacyReco:
    """Imite ``tools.domain._legacy.Reco`` sans la dépendance."""
    title: str
    episode_guid: str | None = None
    creator: str | None = None
    timestamp: str | None = None


class TestLegacyRecosToExtracted:
    def test_basic(self) -> None:
        recos = [_FakeLegacyReco(title="Drive", creator="Refn")]
        out = legacy_recos_to_extracted(recos)
        assert out[0].title == "Drive"
        assert out[0].creator == "Refn"

    def test_skips_blank_title(self) -> None:
        out = legacy_recos_to_extracted([_FakeLegacyReco(title="")])
        assert out == []


class TestLegacyRecoExtractionSource:
    def test_implements_protocol(self) -> None:
        src = LegacyRecoExtractionSource(by_guid={})
        assert isinstance(src, ExtractionSource)

    def test_groups_by_guid(self) -> None:
        recos = [
            _FakeLegacyReco(title="A", episode_guid="ep1"),
            _FakeLegacyReco(title="B", episode_guid="ep1"),
            _FakeLegacyReco(title="C", episode_guid="ep2"),
        ]
        src = LegacyRecoExtractionSource.from_legacy(recos)
        assert sorted(src.episode_guids()) == ["ep1", "ep2"]
        assert len(list(src.for_episode("ep1"))) == 2

    def test_skips_no_guid(self) -> None:
        src = LegacyRecoExtractionSource.from_legacy([
            _FakeLegacyReco(title="X", episode_guid=None),
        ])
        assert list(src.episode_guids()) == []

    def test_unknown_guid_returns_empty(self) -> None:
        src = LegacyRecoExtractionSource(by_guid={})
        assert list(src.for_episode("ghost")) == []
