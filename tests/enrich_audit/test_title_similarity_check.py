"""Tests : tools.enrich_audit.title_similarity_check.

Vérifie le check de similarité titre item ↔ titres TMDB.
Pas d'IO, fonction pure.
"""
from __future__ import annotations

from domain.item import ExternalIds, Item, ItemType
from enrich_audit.title_similarity_check import (
    _normalize,
    check_title_similarity,
)
from enrich_audit.types import Severity


def _item(title: str, *, tmdb: int | None = 42, types=(ItemType.FILM,)) -> Item:
    return Item(
        id="abc12345",
        types=types,
        title=title,
        external_ids=ExternalIds(tmdb=tmdb, tmdb_type="movie") if tmdb else ExternalIds(),
    )


def test_identical_titles_returns_none():
    suspicion = check_title_similarity(_item("Inception"), {"original_title": "Inception"})
    assert suspicion is None


def test_close_titles_above_threshold_returns_none():
    suspicion = check_title_similarity(
        _item("L'amour, c'est surcoté"),
        {"original_title": "L'amour c'est surcote"},
    )
    assert suspicion is None


def test_completely_different_titles_returns_suspicion():
    suspicion = check_title_similarity(
        _item("Inception"),
        {"original_title": "The Godfather"},
    )
    assert suspicion is not None
    assert suspicion.kind == "title_mismatch"
    assert "Inception" in suspicion.detail
    assert "Godfather" in suspicion.detail
    assert suspicion.severity is Severity.WARNING


def test_threshold_is_configurable():
    suspicion = check_title_similarity(
        _item("Cats"),
        {"original_title": "Dogs"},
        threshold=0.1,
    )
    assert suspicion is None


def test_missing_original_title_falls_back_to_title_field():
    suspicion = check_title_similarity(
        _item("Inception"),
        {"title": "Inception"},
    )
    assert suspicion is None


def test_no_tmdb_title_at_all_returns_none():
    assert check_title_similarity(_item("Inception"), {}) is None


def test_uses_tv_name_field_for_series():
    item = Item(id="ab12cd34", types=(ItemType.SERIES,), title="Severance")
    suspicion = check_title_similarity(item, {"name": "Severance"})
    assert suspicion is None


def test_picks_best_among_all_tmdb_titles():
    """CR senior H1 : on prend le ratio MAX sur l'union des titres.

    « Les Nouveaux Sauvages » (FR) ↔ « Relatos salvajes » (ES, original) :
    en checant seulement `original_title` on a un faux positif. Mais TMDB
    expose aussi `title` (FR) → le ratio max passe le seuil.
    """
    suspicion = check_title_similarity(
        _item("Les Nouveaux Sauvages"),
        {
            "original_title": "Relatos salvajes",
            "title": "Les Nouveaux Sauvages",
        },
    )
    assert suspicion is None


def test_detail_mentions_count_of_titles_checked():
    """Aide au debug : le détail liste combien de titres ont été comparés."""
    suspicion = check_title_similarity(
        _item("Inception"),
        {"original_title": "AAA", "title": "BBB"},
    )
    assert suspicion is not None
    assert "essayés=2" in suspicion.detail


def test_confidence_reflects_distance_from_threshold():
    suspicion = check_title_similarity(
        _item("Inception"),
        {"original_title": "The Godfather"},
    )
    assert suspicion is not None
    assert suspicion.confidence is not None
    assert 0.0 <= suspicion.confidence <= 1.0


# ===== _normalize (CR senior L1 : ligatures) ===============================


def test_normalize_handles_oe_ligature():
    """œ ne doit pas être perdu : `cœur` ↔ `coeur`."""
    assert _normalize("cœur") == _normalize("coeur")


def test_normalize_handles_ae_ligature():
    assert _normalize("Cæsar") == _normalize("Caesar")


def test_normalize_handles_eszett():
    assert _normalize("Straße") == _normalize("Strasse")


def test_normalize_collapses_whitespace():
    assert _normalize("a   b\tc") == "a b c"


def test_normalize_strips_punctuation():
    assert _normalize("Hello, world!") == "hello world"
