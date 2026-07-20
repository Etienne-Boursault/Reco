"""Tests : tools.enrich_audit.thresholds — source unique de vérité (CR M8)."""
from __future__ import annotations

from enrich_audit import thresholds


def test_thresholds_are_floats_or_ints():
    assert isinstance(thresholds.DEFAULT_TITLE_THRESHOLD, float)
    assert isinstance(thresholds.DEFAULT_YEAR_TOLERANCE, int)
    assert isinstance(thresholds.DEFAULT_FILM_MIN_RUNTIME, int)
    assert isinstance(thresholds.DEFAULT_SERIES_EPISODE_MAX_RUNTIME, int)
    assert isinstance(thresholds.DEFAULT_SERIES_EPISODE_MIN_RUNTIME, int)


def test_title_threshold_within_unit_interval():
    assert 0.0 < thresholds.DEFAULT_TITLE_THRESHOLD < 1.0


def test_year_tolerance_is_non_negative():
    assert thresholds.DEFAULT_YEAR_TOLERANCE >= 0


def test_film_min_runtime_is_low_enough_for_shorts():
    """CR senior H3 : seuil abaissé pour éviter les faux positifs courts."""
    assert thresholds.DEFAULT_FILM_MIN_RUNTIME <= 25


def test_series_runtime_bounds_consistent():
    assert (
        thresholds.DEFAULT_SERIES_EPISODE_MIN_RUNTIME
        < thresholds.DEFAULT_SERIES_EPISODE_MAX_RUNTIME
    )


def test_series_max_lower_than_legacy_240():
    """CR senior H2 : abaissé de 240 vers ~180."""
    assert thresholds.DEFAULT_SERIES_EPISODE_MAX_RUNTIME <= 200
