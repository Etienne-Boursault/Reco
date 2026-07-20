"""Tests : tools.enrich_audit.runtime_coherence_check."""
from __future__ import annotations

from domain.item import Item, ItemType
from enrich_audit.runtime_coherence_check import check_runtime_coherence
from enrich_audit.thresholds import (
    DEFAULT_FILM_MIN_RUNTIME,
    DEFAULT_SERIES_EPISODE_MAX_RUNTIME,
    DEFAULT_SERIES_EPISODE_MIN_RUNTIME,
)
from enrich_audit.types import Severity


def _item(types: tuple[ItemType, ...]) -> Item:
    return Item(id="abc12345", types=types, title="X")


def test_film_with_normal_runtime_returns_none():
    assert check_runtime_coherence(_item((ItemType.FILM,)), {"runtime": 95}) is None


def test_film_with_short_runtime_returns_suspicion():
    """runtime < DEFAULT_FILM_MIN_RUNTIME sur un film → court probable."""
    short = DEFAULT_FILM_MIN_RUNTIME - 1
    suspicion = check_runtime_coherence(_item((ItemType.FILM,)), {"runtime": short})
    assert suspicion is not None
    assert suspicion.kind == "runtime_short_film"
    assert str(short) in suspicion.detail
    # CR senior H3 : reformulé "à vérifier" → INFO.
    assert suspicion.severity is Severity.INFO


def test_film_runtime_exactly_at_threshold_is_ok():
    assert check_runtime_coherence(
        _item((ItemType.FILM,)),
        {"runtime": DEFAULT_FILM_MIN_RUNTIME},
    ) is None


def test_film_runtime_threshold_injectable():
    """CR senior H4 : seuil injectable."""
    suspicion = check_runtime_coherence(
        _item((ItemType.FILM,)),
        {"runtime": 25},
        film_min_runtime=40,
    )
    assert suspicion is not None  # 25 < 40 → suspect avec seuil custom


def test_series_with_long_total_runtime_returns_suspicion():
    """Épisode > DEFAULT_SERIES_EPISODE_MAX_RUNTIME → TV-movie suspect."""
    long_rt = DEFAULT_SERIES_EPISODE_MAX_RUNTIME + 1
    suspicion = check_runtime_coherence(
        _item((ItemType.SERIES,)),
        {"episode_run_time": [long_rt]},
    )
    assert suspicion is not None
    assert suspicion.kind == "runtime_long_series"
    assert suspicion.severity is Severity.WARNING


def test_series_with_very_short_episode_returns_info():
    """CR senior H2 : épisode < DEFAULT_SERIES_EPISODE_MIN_RUNTIME → cartoon court."""
    short_rt = DEFAULT_SERIES_EPISODE_MIN_RUNTIME - 1
    suspicion = check_runtime_coherence(
        _item((ItemType.SERIES,)),
        {"episode_run_time": [short_rt]},
    )
    assert suspicion is not None
    assert suspicion.kind == "runtime_short_series"
    assert suspicion.severity is Severity.INFO


def test_series_with_normal_runtime_returns_none():
    suspicion = check_runtime_coherence(
        _item((ItemType.SERIES,)),
        {"episode_run_time": [45]},
    )
    assert suspicion is None


def test_other_types_are_ignored():
    assert check_runtime_coherence(_item((ItemType.BOOK,)), {"runtime": 5}) is None
    assert check_runtime_coherence(_item((ItemType.MUSIC,)), {"runtime": 999}) is None


def test_missing_runtime_is_noop():
    assert check_runtime_coherence(_item((ItemType.FILM,)), {}) is None
    assert check_runtime_coherence(_item((ItemType.SERIES,)), {"episode_run_time": []}) is None
    assert check_runtime_coherence(_item((ItemType.FILM,)), {"runtime": 0}) is None


def test_series_with_only_invalid_episode_runtimes_is_noop():
    suspicion = check_runtime_coherence(
        _item((ItemType.SERIES,)),
        {"episode_run_time": [0, -5, "bogus", True]},
    )
    assert suspicion is None


def test_film_runtime_non_int_is_noop():
    assert check_runtime_coherence(_item((ItemType.FILM,)), {"runtime": True}) is None
    assert check_runtime_coherence(_item((ItemType.FILM,)), {"runtime": "90"}) is None


def test_multi_type_item_film_check_applies():
    """Item taggé [film, livre] : le check film s'applique."""
    suspicion = check_runtime_coherence(
        _item((ItemType.FILM, ItemType.BOOK)),
        {"runtime": 10},
    )
    assert suspicion is not None
