"""Tests : tools.enrich_audit.tmdb_type_mismatch_check.

CR senior C5 — c'est le check critique : il détecte le mauvais shape du
payload TMDB par rapport au type éditorial de l'Item.
"""
from __future__ import annotations

from domain.item import ExternalIds, Item, ItemType
from enrich_audit.tmdb_type_mismatch_check import (
    _detect_tmdb_shape,
    check_tmdb_type_mismatch,
)
from enrich_audit.types import Severity


def _film(*, declared: str | None = "movie") -> Item:
    return Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="X",
        external_ids=ExternalIds(tmdb=1, tmdb_type=declared),
    )


def _series(*, declared: str | None = "tv") -> Item:
    return Item(
        id="abc12345",
        types=(ItemType.SERIES,),
        title="X",
        external_ids=ExternalIds(tmdb=1, tmdb_type=declared),
    )


# ===== _detect_tmdb_shape ===================================================


def test_detect_shape_movie_via_release_date():
    assert _detect_tmdb_shape({"release_date": "2010-01-01"}) == "movie"


def test_detect_shape_tv_via_first_air_date():
    assert _detect_tmdb_shape({"first_air_date": "2010-01-01"}) == "tv"


def test_detect_shape_movie_via_runtime():
    assert _detect_tmdb_shape({"runtime": 120, "title": "X"}) == "movie"


def test_detect_shape_tv_via_episode_run_time():
    assert _detect_tmdb_shape({"episode_run_time": [45]}) == "tv"


def test_detect_shape_ambiguous_returns_none():
    """Champs des deux côtés → on s'abstient."""
    assert _detect_tmdb_shape({"title": "X", "name": "Y"}) is None


def test_detect_shape_empty_returns_none():
    assert _detect_tmdb_shape({}) is None


# ===== check ================================================================


def test_film_with_movie_payload_is_clean():
    item = _film()
    assert check_tmdb_type_mismatch(
        item,
        {"original_title": "X", "release_date": "2010-01-01"},
    ) is None


def test_series_with_tv_payload_is_clean():
    item = _series()
    assert check_tmdb_type_mismatch(
        item,
        {"name": "X", "first_air_date": "2010-01-01"},
    ) is None


def test_film_with_tv_payload_is_critical():
    """Item taggé film mais payload TMDB de type série → CRITIQUE."""
    item = _film()
    suspicion = check_tmdb_type_mismatch(
        item,
        {"name": "X", "first_air_date": "2010-01-01"},
    )
    assert suspicion is not None
    assert suspicion.kind == "tmdb_type_mismatch"
    assert suspicion.severity is Severity.CRITICAL


def test_series_with_movie_payload_is_critical():
    item = _series()
    suspicion = check_tmdb_type_mismatch(
        item,
        {"title": "X", "release_date": "2010-01-01"},
    )
    assert suspicion is not None
    assert suspicion.kind == "tmdb_type_mismatch"
    assert suspicion.severity is Severity.CRITICAL


def test_book_item_is_noop():
    """Item non-vidéo → check non applicable."""
    item = Item(id="abc12345", types=(ItemType.BOOK,), title="X")
    assert check_tmdb_type_mismatch(item, {"release_date": "2010"}) is None


def test_film_and_series_multi_type_is_tolerated():
    """Cas multi-type rare (anthologies hybrides) → on tolère."""
    item = Item(
        id="abc12345",
        types=(ItemType.FILM, ItemType.SERIES),
        title="X",
    )
    assert check_tmdb_type_mismatch(
        item,
        {"name": "X", "first_air_date": "2010-01-01"},
    ) is None


def test_ambiguous_shape_falls_back_to_declared_type():
    """Si shape ambigu, on s'appuie sur item.external_ids.tmdb_type."""
    item = _film(declared="tv")  # Item est film mais déclaré "tv" TMDB
    suspicion = check_tmdb_type_mismatch(
        item,
        {"title": "X", "name": "Y"},  # ambigu
    )
    assert suspicion is not None
    assert suspicion.kind == "tmdb_type_mismatch"


def test_ambiguous_shape_no_declared_type_is_noop():
    """Shape ambigu + pas de tmdb_type déclaré → on s'abstient."""
    item = Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="X",
        external_ids=ExternalIds(tmdb=1, tmdb_type=None),
    )
    assert check_tmdb_type_mismatch(
        item,
        {"title": "X", "name": "Y"},
    ) is None


def test_check_metadata_protocol():
    """CR archi P0 #1 : check expose name/kind/description."""
    assert check_tmdb_type_mismatch.name == "tmdb_type_mismatch"  # type: ignore[attr-defined]
    assert check_tmdb_type_mismatch.kind == "tmdb_type_mismatch"  # type: ignore[attr-defined]
    assert "type" in check_tmdb_type_mismatch.description.lower()  # type: ignore[attr-defined]
