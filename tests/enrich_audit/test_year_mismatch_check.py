"""Tests : tools.enrich_audit.year_mismatch_check."""
from __future__ import annotations

from domain.item import Item, ItemType
from enrich_audit.types import Severity
from enrich_audit.year_mismatch_check import check_year_mismatch


def _item(year: int | None) -> Item:
    return Item(id="abc12345", types=(ItemType.FILM,), title="X", year=year)


def test_same_year_returns_none():
    assert check_year_mismatch(_item(2010), {"release_date": "2010-07-16"}) is None


def test_within_tolerance_returns_none():
    assert check_year_mismatch(_item(2010), {"release_date": "2011-07-16"}) is None
    assert check_year_mismatch(_item(2010), {"release_date": "2009-12-31"}) is None


def test_outside_tolerance_returns_suspicion():
    suspicion = check_year_mismatch(_item(2010), {"release_date": "2020-01-01"})
    assert suspicion is not None
    assert suspicion.kind == "year_mismatch"
    assert "2010" in suspicion.detail and "2020" in suspicion.detail
    # delta=10 → WARNING (>10 = CRITICAL).
    assert suspicion.severity is Severity.WARNING


def test_large_delta_returns_critical():
    suspicion = check_year_mismatch(_item(1980), {"release_date": "2020-01-01"})
    assert suspicion is not None
    assert suspicion.severity is Severity.CRITICAL


def test_item_without_year_is_noop():
    assert check_year_mismatch(_item(None), {"release_date": "2020-01-01"}) is None


def test_tmdb_without_year_is_noop():
    assert check_year_mismatch(_item(2010), {}) is None
    assert check_year_mismatch(_item(2010), {"release_date": ""}) is None


def test_tv_uses_first_air_date():
    suspicion = check_year_mismatch(_item(2010), {"first_air_date": "2010-09-01"})
    assert suspicion is None
    suspicion = check_year_mismatch(_item(2010), {"first_air_date": "2024-09-01"})
    assert suspicion is not None and suspicion.kind == "year_mismatch"


def test_custom_tolerance():
    assert check_year_mismatch(_item(2010), {"release_date": "2015-01-01"}, tolerance=5) is None


def test_malformed_date_is_noop():
    """Date TMDB invalide → no-op."""
    assert check_year_mismatch(_item(2010), {"release_date": "not-a-date"}) is None


def test_malformed_date_with_extra_chars_is_noop():
    """CR senior L2 : `"2010Z"` n'est plus accepté comme année 2010."""
    assert check_year_mismatch(_item(2010), {"release_date": "2010Z"}) is None
    assert check_year_mismatch(_item(2010), {"release_date": "2010 bogus"}) is None


def test_year_only_format_is_accepted():
    """Format `YYYY` accepté (TMDB renvoie parfois seulement l'année)."""
    assert check_year_mismatch(_item(2010), {"release_date": "2010"}) is None
