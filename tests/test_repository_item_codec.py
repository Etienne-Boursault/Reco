"""Tests de `tools.repository.serialization.item_codec` — codecs purs (zéro IO).

Couverture 100% requise. TDD strict : ces tests décrivent le contrat
de sérialisation Item ↔ dict JSON, indépendamment de tout backend.
"""
from __future__ import annotations

import pytest

from domain.item import (
    CustomLink,
    ExternalIds,
    Item,
    ItemType,
    WatchProvider,
)
from repository.serialization.item_codec import (
    item_from_dict,
    item_to_dict,
)


# ---------------------------------------------------------------------------
# Round-trip — 5 cas variés
# ---------------------------------------------------------------------------


def test_round_trip_minimal_item():
    item = Item(id="abc12345", types=(ItemType.FILM,), title="Titanic")
    assert item_from_dict(item_to_dict(item)) == item


def test_round_trip_full_item():
    item = Item(
        id="def67890",
        types=(ItemType.FILM, ItemType.SERIES),
        title="Le Seigneur des Anneaux",
        creator="Peter Jackson",
        year=2001,
        aliases=("LOTR", "Lord of the Rings"),
        external_ids=ExternalIds(
            tmdb=120, tmdb_type="movie", spotify="abc", musicbrainz="xx",
            openlibrary="OL1", isbn="978", justwatch="jw1",
        ),
        custom_links=(CustomLink(label="Wiki", url="https://wiki.example.com"),),
        watch_providers=(
            WatchProvider(name="Netflix", url="https://netflix.com/x", region="FR"),
            WatchProvider(name="Prime", url="https://prime.example.com"),
        ),
        link_overrides={"JustWatch": "https://jw.example.com/custom"},
        recommended_by="Kyan",
        schema_version=1,
    )
    assert item_from_dict(item_to_dict(item)) == item


def test_round_trip_book():
    item = Item(
        id="boo00001",
        types=(ItemType.BOOK,),
        title="Le Petit Prince",
        creator="Saint-Exupéry",
        year=1943,
    )
    assert item_from_dict(item_to_dict(item)) == item


def test_round_trip_artist_no_year():
    item = Item(id="art11111", types=(ItemType.ARTIST,), title="Daft Punk")
    assert item_from_dict(item_to_dict(item)) == item


def test_round_trip_with_link_overrides_only():
    item = Item(
        id="ovr22222",
        types=(ItemType.MUSIC,),
        title="One More Time",
        link_overrides={"Spotify": "https://open.spotify.com/track/x"},
    )
    assert item_from_dict(item_to_dict(item)) == item


# ---------------------------------------------------------------------------
# to_dict — comportement
# ---------------------------------------------------------------------------


def test_to_dict_camelcase_keys():
    item = Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="T",
        external_ids=ExternalIds(tmdb=1, tmdb_type="movie"),
    )
    d = item_to_dict(item)
    # Doit utiliser camelCase pour cohérence schémas Astro
    assert "externalIds" in d
    assert "tmdbType" in d["externalIds"]
    assert "tmdb_type" not in d["externalIds"]
    assert "schemaVersion" in d


def test_to_dict_omits_none_creator_and_year():
    item = Item(id="abc12345", types=(ItemType.FILM,), title="T")
    d = item_to_dict(item)
    # creator et year None → omis (compatibilité Zod .optional())
    assert "creator" not in d
    assert "year" not in d


def test_to_dict_omits_empty_optional_collections():
    item = Item(id="abc12345", types=(ItemType.FILM,), title="T")
    d = item_to_dict(item)
    # aliases vide → omis
    assert "aliases" not in d
    assert "customLinks" not in d
    assert "watchProviders" not in d
    assert "linkOverrides" not in d
    assert "recommendedBy" not in d


def test_to_dict_omits_empty_external_ids():
    item = Item(id="abc12345", types=(ItemType.FILM,), title="T")
    d = item_to_dict(item)
    # externalIds par défaut (tout None) → omis
    assert "externalIds" not in d


def test_to_dict_keeps_partial_external_ids():
    item = Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="T",
        external_ids=ExternalIds(tmdb=42),
    )
    d = item_to_dict(item)
    assert d["externalIds"] == {"tmdb": 42}
    # autres champs None → omis du sous-dict
    assert "spotify" not in d["externalIds"]


def test_to_dict_types_as_strings():
    item = Item(id="abc12345", types=(ItemType.FILM, ItemType.SERIES), title="T")
    d = item_to_dict(item)
    assert d["types"] == ["film", "serie"]


def test_to_dict_custom_links_serialized():
    item = Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="T",
        custom_links=(CustomLink(label="X", url="https://x.example.com"),),
    )
    d = item_to_dict(item)
    assert d["customLinks"] == [{"label": "X", "url": "https://x.example.com"}]


def test_to_dict_watch_providers_serialized():
    item = Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="T",
        watch_providers=(
            WatchProvider(name="N", url="https://n.example.com", region="FR"),
            WatchProvider(name="P", url="https://p.example.com"),
        ),
    )
    d = item_to_dict(item)
    assert d["watchProviders"][0] == {
        "name": "N", "url": "https://n.example.com", "region": "FR",
    }
    # region None → omis
    assert d["watchProviders"][1] == {"name": "P", "url": "https://p.example.com"}


def test_to_dict_link_overrides_as_dict():
    item = Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="T",
        link_overrides={"K": "https://v.example.com"},
    )
    d = item_to_dict(item)
    assert d["linkOverrides"] == {"K": "https://v.example.com"}


def test_to_dict_aliases_as_list():
    item = Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="T",
        aliases=("A", "B"),
    )
    d = item_to_dict(item)
    assert d["aliases"] == ["A", "B"]


# ---------------------------------------------------------------------------
# from_dict — validation et erreurs
# ---------------------------------------------------------------------------


def test_from_dict_missing_id_raises():
    with pytest.raises((KeyError, ValueError)):
        item_from_dict({"types": ["film"], "title": "T"})


def test_from_dict_missing_types_raises():
    with pytest.raises((KeyError, ValueError)):
        item_from_dict({"id": "abc12345", "title": "T"})


def test_from_dict_missing_title_raises():
    with pytest.raises((KeyError, ValueError)):
        item_from_dict({"id": "abc12345", "types": ["film"]})


def test_from_dict_unknown_field_is_tolerated():
    """Forward compat soft (cf. config_loader) : un champ inconnu est ignoré."""
    d = {
        "id": "abc12345",
        "types": ["film"],
        "title": "T",
        "schemaVersion": 1,
        "futureField": "ignored",
    }
    item = item_from_dict(d)
    assert item.id == "abc12345"


def test_unknown_field_logged_with_warning(caplog):
    """A11 — Forward-compat capture : warning structuré sur champs inconnus."""
    import logging
    d = {
        "id": "abc12345",
        "types": ["film"],
        "title": "T",
        "futureA": 1,
        "futureB": "x",
    }
    with caplog.at_level(logging.WARNING, logger="repository.serialization.item_codec"):
        item_from_dict(d)
    msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("champs inconnus" in m and "futureA" in m and "futureB" in m for m in msgs)
    assert any("abc12345" in m for m in msgs)


def test_known_fields_no_warning(caplog):
    """A11 — Aucun warning si seuls les champs reconnus sont présents."""
    import logging
    d = {
        "id": "abc12345",
        "types": ["film"],
        "title": "T",
        "schemaVersion": 1,
    }
    with caplog.at_level(logging.WARNING, logger="repository.serialization.item_codec"):
        item_from_dict(d)
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_from_dict_invalid_id_raises():
    with pytest.raises(ValueError):
        item_from_dict({"id": "Invalid!", "types": ["film"], "title": "T"})


def test_from_dict_invalid_type_raises():
    with pytest.raises(ValueError):
        item_from_dict({"id": "abc12345", "types": ["not-a-type"], "title": "T"})


def test_from_dict_external_ids_round_trip():
    ext = ExternalIds(
        tmdb=42, tmdb_type="tv", spotify="s", musicbrainz="mb",
        openlibrary="ol", isbn="i", justwatch="jw",
    )
    item = Item(
        id="abc12345", types=(ItemType.FILM,), title="T", external_ids=ext,
    )
    d = item_to_dict(item)
    assert item_from_dict(d).external_ids == ext


def test_from_dict_external_ids_partial():
    d = {
        "id": "abc12345",
        "types": ["film"],
        "title": "T",
        "externalIds": {"tmdb": 7, "tmdbType": "movie"},
    }
    item = item_from_dict(d)
    assert item.external_ids.tmdb == 7
    assert item.external_ids.tmdb_type == "movie"
    assert item.external_ids.spotify is None


def test_from_dict_watch_providers_with_region():
    d = {
        "id": "abc12345",
        "types": ["film"],
        "title": "T",
        "watchProviders": [
            {"name": "N", "url": "https://n.example.com", "region": "FR"},
        ],
    }
    item = item_from_dict(d)
    assert item.watch_providers[0].region == "FR"


def test_ethics_round_trip():
    """B8 — `ethics` est préservé au passage to_dict/from_dict."""
    item = Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="T",
        watch_providers=(
            WatchProvider(name="N", url="https://n.example.com", ethics="indie"),
            WatchProvider(name="A", url="https://a.example.com", ethics="avoid"),
            WatchProvider(name="Z", url="https://z.example.com"),
        ),
    )
    d = item_to_dict(item)
    assert d["watchProviders"][0]["ethics"] == "indie"
    assert d["watchProviders"][1]["ethics"] == "avoid"
    assert "ethics" not in d["watchProviders"][2]  # None omis
    restored = item_from_dict(d)
    assert restored == item


def test_from_dict_watch_providers_without_region():
    d = {
        "id": "abc12345",
        "types": ["film"],
        "title": "T",
        "watchProviders": [{"name": "N", "url": "https://n.example.com"}],
    }
    item = item_from_dict(d)
    assert item.watch_providers[0].region is None


def test_from_dict_custom_links_round_trip():
    d = {
        "id": "abc12345",
        "types": ["film"],
        "title": "T",
        "customLinks": [{"label": "L", "url": "https://u.example.com"}],
    }
    item = item_from_dict(d)
    assert item.custom_links == (CustomLink(label="L", url="https://u.example.com"),)


def test_from_dict_link_overrides_round_trip():
    d = {
        "id": "abc12345",
        "types": ["film"],
        "title": "T",
        "linkOverrides": {"K": "https://v.example.com"},
    }
    item = item_from_dict(d)
    assert dict(item.link_overrides) == {"K": "https://v.example.com"}


def test_from_dict_aliases_as_tuple():
    d = {"id": "abc12345", "types": ["film"], "title": "T", "aliases": ["a", "b"]}
    item = item_from_dict(d)
    assert item.aliases == ("a", "b")


def test_from_dict_schema_version_default():
    d = {"id": "abc12345", "types": ["film"], "title": "T"}
    item = item_from_dict(d)
    assert item.schema_version == 1


def test_from_dict_schema_version_explicit():
    d = {"id": "abc12345", "types": ["film"], "title": "T", "schemaVersion": 2}
    item = item_from_dict(d)
    assert item.schema_version == 2


def test_from_dict_recommended_by():
    d = {
        "id": "abc12345", "types": ["film"], "title": "T",
        "recommendedBy": "Kyan",
    }
    item = item_from_dict(d)
    assert item.recommended_by == "Kyan"
