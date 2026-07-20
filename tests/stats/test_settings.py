"""Tests pour ``tools.stats.settings.StatsSettings`` (R-P1-25)."""
from __future__ import annotations

import pytest

from stats.settings import (
    DEFAULT_HIDDEN_STATUSES,
    DEFAULT_TOP_GUESTS_LIMIT,
    DEFAULT_TOP_WORKS_LIMIT,
    StatsSettings,
)


def test_defaults():
    s = StatsSettings()
    assert s.top_guests_limit == DEFAULT_TOP_GUESTS_LIMIT
    assert s.top_works_limit == DEFAULT_TOP_WORKS_LIMIT
    assert s.hidden_statuses == DEFAULT_HIDDEN_STATUSES


def test_rejects_zero_limit():
    with pytest.raises(ValueError):
        StatsSettings(top_guests_limit=0)
    with pytest.raises(ValueError):
        StatsSettings(top_works_limit=-1)


def test_rejects_non_int_limit():
    with pytest.raises(ValueError):
        StatsSettings(top_guests_limit="10")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        StatsSettings(top_guests_limit=True)  # bool rejeté


def test_rejects_empty_hidden_statuses():
    with pytest.raises(ValueError):
        StatsSettings(hidden_statuses=())


def test_rejects_invalid_hidden_statuses_entry():
    with pytest.raises(ValueError):
        StatsSettings(hidden_statuses=("",))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        StatsSettings(hidden_statuses=(123,))  # type: ignore[arg-type]


def test_from_source_extra_none_uses_defaults():
    s = StatsSettings.from_source_extra(None)
    assert s == StatsSettings()


def test_from_source_extra_reads_payload():
    extra = {
        "stats": {
            "top_guests_limit": 50,
            "top_works_limit": 25,
            "hidden_statuses": ["discarded", "flagged"],
        }
    }
    s = StatsSettings.from_source_extra(extra)
    assert s.top_guests_limit == 50
    assert s.top_works_limit == 25
    assert s.hidden_statuses == ("discarded", "flagged")


def test_from_source_extra_overrides_win():
    extra = {"stats": {"top_guests_limit": 5}}
    s = StatsSettings.from_source_extra(extra, overrides={"top_guests_limit": 99})
    assert s.top_guests_limit == 99


def test_from_source_extra_ignores_unknown_keys():
    """Forward-compat : clé inconnue ne lève pas (un fork peut ajouter)."""
    extra = {"stats": {"top_guests_limit": 7, "future_field": "xx"}}
    s = StatsSettings.from_source_extra(extra)
    assert s.top_guests_limit == 7


def test_rejects_non_tuple_hidden_after_coercion():
    """Si on bypass `from_source_extra`, set direct → erreur."""
    with pytest.raises(ValueError):
        StatsSettings(hidden_statuses=["discarded"])  # type: ignore[arg-type]
