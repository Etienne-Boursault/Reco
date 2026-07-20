"""Tests de `tools.domain.services.compatibility` — couverture 100%."""
from __future__ import annotations

import pytest

from domain.item import ExternalIds, Item, ItemType
from domain.mention import Mention, SourceRef
from domain.services.compatibility import can_attach_mention, can_merge_items


def _make_item(**overrides):
    base = dict(
        id="abc12345",
        types=(ItemType.FILM,),
        title="Drive",
        creator="Refn",
    )
    base.update(overrides)
    return Item(**base)


# ---------------------------------------------------------------------------
# can_merge_items
# ---------------------------------------------------------------------------


def test_can_merge_identical_items():
    a = _make_item()
    b = _make_item(id="def67890")
    assert can_merge_items(a, b) is True


def test_can_merge_normalized_title_match():
    a = _make_item(title="Drive!", creator="Refn")
    b = _make_item(id="def67890", title="drive", creator="REFN")
    assert can_merge_items(a, b) is True


def test_can_merge_different_canonical_returns_false():
    a = _make_item(title="Drive")
    b = _make_item(id="def67890", title="Other")
    assert can_merge_items(a, b) is False


def test_can_merge_different_creator_returns_false():
    a = _make_item(creator="Refn")
    b = _make_item(id="def67890", creator="Different")
    assert can_merge_items(a, b) is False


def test_can_merge_disjoint_types_returns_false():
    a = _make_item(types=(ItemType.FILM,))
    b = _make_item(id="def67890", types=(ItemType.SERIES,))
    # canonical_key inclut les types triés → seront forcément différents,
    # donc on rejette dès l'étape canonical. C'est cohérent : un FILM et
    # une SERIES sont des œuvres distinctes même si titre identique.
    assert can_merge_items(a, b) is False


def test_can_merge_overlapping_types_returns_true():
    a = _make_item(types=(ItemType.FILM, ItemType.SERIES))
    b = _make_item(id="def67890", types=(ItemType.FILM, ItemType.SERIES))
    assert can_merge_items(a, b) is True


def test_can_merge_external_ids_conflict_returns_false():
    a = _make_item(external_ids=ExternalIds(tmdb=42, tmdb_type="movie"))
    b = _make_item(
        id="def67890", external_ids=ExternalIds(tmdb=43, tmdb_type="movie")
    )
    assert can_merge_items(a, b) is False


def test_can_merge_partial_external_ids_returns_true():
    # L'un a tmdb, l'autre non → pas de conflit → fusion possible.
    a = _make_item(external_ids=ExternalIds(tmdb=42, tmdb_type="movie"))
    b = _make_item(id="def67890", external_ids=ExternalIds())
    assert can_merge_items(a, b) is True


def test_can_merge_same_external_ids_returns_true():
    a = _make_item(external_ids=ExternalIds(tmdb=42, tmdb_type="movie", spotify="abc"))
    b = _make_item(
        id="def67890",
        external_ids=ExternalIds(tmdb=42, tmdb_type="movie", spotify="abc"),
    )
    assert can_merge_items(a, b) is True


def test_can_merge_spotify_conflict_returns_false():
    a = _make_item(external_ids=ExternalIds(spotify="aaa"))
    b = _make_item(id="def67890", external_ids=ExternalIds(spotify="bbb"))
    assert can_merge_items(a, b) is False


def test_can_merge_isbn_conflict_returns_false():
    a = _make_item(external_ids=ExternalIds(isbn="111"))
    b = _make_item(id="def67890", external_ids=ExternalIds(isbn="222"))
    assert can_merge_items(a, b) is False


def test_can_merge_non_item_raises():
    a = _make_item()
    with pytest.raises(ValueError, match="Item"):
        can_merge_items(a, "not-an-item")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Item"):
        can_merge_items("not-an-item", a)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# can_attach_mention
# ---------------------------------------------------------------------------


def test_can_attach_mention_matching_ids_returns_true():
    item = _make_item(id="abc12345")
    mention = Mention(
        id="m-1", item_id="abc12345", source_ref=SourceRef(source_id="ubm")
    )
    assert can_attach_mention(mention, item) is True


def test_can_attach_mention_different_ids_returns_false():
    item = _make_item(id="abc12345")
    mention = Mention(
        id="m-1", item_id="other-id", source_ref=SourceRef(source_id="ubm")
    )
    assert can_attach_mention(mention, item) is False


def test_can_attach_mention_non_mention_raises():
    item = _make_item()
    with pytest.raises(ValueError, match="types invalides"):
        can_attach_mention("not-a-mention", item)  # type: ignore[arg-type]


def test_can_attach_mention_non_item_raises():
    mention = Mention(
        id="m-1", item_id="abc12345", source_ref=SourceRef(source_id="ubm")
    )
    with pytest.raises(ValueError, match="types invalides"):
        can_attach_mention(mention, "not-an-item")  # type: ignore[arg-type]
