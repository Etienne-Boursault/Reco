"""Tests : tools.match_audit.protocols."""
from __future__ import annotations

import pytest

from tools.match_audit.protocols import EpisodeView


def test_view_from_dict_minimal():
    v = EpisodeView.from_dict({"guid": "abc"})
    assert v is not None
    assert v.guid == "abc"
    assert v.title is None
    assert v.audio_duration is None


def test_view_from_dict_picks_str_title():
    v = EpisodeView.from_dict({"guid": "abc", "title": "T", "youtubeTitle": "YT"})
    assert v is not None
    assert v.title == "T"
    assert v.youtube_title == "YT"


def test_view_from_dict_rejects_non_str_title_silently():
    v = EpisodeView.from_dict({"guid": "abc", "title": 42})
    assert v is not None
    assert v.title is None


def test_view_from_dict_rejects_bool_as_int():
    """bool() est un int en Python — on doit l'écarter."""
    v = EpisodeView.from_dict({"guid": "abc", "audioDuration": True})
    assert v is not None
    assert v.audio_duration is None


def test_view_from_dict_no_guid_returns_none():
    """CR senior C1 — payload sans guid → None, pas une view 'vide'."""
    assert EpisodeView.from_dict({"title": "x"}) is None
    assert EpisodeView.from_dict({"guid": ""}) is None
    assert EpisodeView.from_dict({"guid": 42}) is None  # type: ignore[arg-type]


def test_view_is_frozen():
    v = EpisodeView.from_dict({"guid": "abc"})
    assert v is not None
    with pytest.raises(Exception):
        v.title = "x"  # type: ignore[misc]


def test_view_post_init_validates_guid():
    with pytest.raises(ValueError):
        EpisodeView(guid="", title=None, youtube_title=None,
                    audio_duration=None, youtube_duration=None, raw={})


def test_view_raw_preserves_original():
    v = EpisodeView.from_dict({"guid": "g", "extra": 42})
    assert v is not None
    assert v.raw["extra"] == 42
