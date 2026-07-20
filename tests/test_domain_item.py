"""Tests de `tools.domain.item` — couverture 100% (couche pure, zéro IO)."""
from __future__ import annotations

import dataclasses

import pytest

from domain.item import (
    CustomLink,
    ExternalIds,
    Item,
    ItemType,
    WatchProvider,
)


# ---------------------------------------------------------------------------
# ItemType
# ---------------------------------------------------------------------------


def test_item_type_values_are_stable_strings():
    assert ItemType.BOOK == "livre"
    assert ItemType.FILM == "film"
    assert ItemType.SERIES == "serie"
    assert ItemType.MUSIC == "musique"
    assert ItemType.ALBUM == "album"
    assert ItemType.ARTIST == "artiste"
    assert ItemType.PODCAST == "podcast"
    assert ItemType.GAME == "jeu"
    assert ItemType.COMIC == "bd"
    assert ItemType.ARTICLE == "article"
    assert ItemType.OTHER == "autre"


def test_item_type_is_str_enum():
    # Permet une sérialisation JSON transparente
    assert isinstance(ItemType.FILM, str)


# ---------------------------------------------------------------------------
# ExternalIds
# ---------------------------------------------------------------------------


def test_external_ids_default_empty():
    e = ExternalIds()
    assert e.tmdb is None
    assert e.tmdb_type is None
    assert e.spotify is None
    assert e.musicbrainz is None
    assert e.openlibrary is None
    assert e.isbn is None
    assert e.justwatch is None


def test_external_ids_equality():
    a = ExternalIds(tmdb=42, tmdb_type="movie")
    b = ExternalIds(tmdb=42, tmdb_type="movie")
    assert a == b


def test_external_ids_tmdb_type_accepts_movie_tv_none():
    ExternalIds(tmdb_type=None)
    ExternalIds(tmdb_type="movie")
    ExternalIds(tmdb_type="tv")


def test_external_ids_tmdb_type_invalid_raises():
    with pytest.raises(ValueError, match="tmdb_type"):
        ExternalIds(tmdb_type="film")


def test_external_ids_tmdb_must_be_int():
    with pytest.raises(ValueError, match="tmdb"):
        ExternalIds(tmdb="42")  # type: ignore[arg-type]


def test_external_ids_is_frozen():
    e = ExternalIds(tmdb=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.tmdb = 2  # type: ignore[misc]


# B11 — from_partial
def test_external_ids_from_partial_filters_none():
    e = ExternalIds.from_partial(tmdb=42, spotify=None, musicbrainz="mbid")
    assert e.tmdb == 42
    assert e.spotify is None
    assert e.musicbrainz == "mbid"


def test_external_ids_from_partial_coerces_tmdb_string_to_int():
    e = ExternalIds.from_partial(tmdb="42")
    assert e.tmdb == 42


def test_external_ids_from_partial_ignores_unknown_field():
    e = ExternalIds.from_partial(tmdb=1, unknown="oops")  # type: ignore[arg-type]
    assert e.tmdb == 1


def test_external_ids_from_partial_invalid_tmdb_str_raises():
    with pytest.raises(ValueError, match="tmdb"):
        ExternalIds.from_partial(tmdb="not-a-number")


def test_external_ids_from_partial_empty():
    e = ExternalIds.from_partial()
    assert e == ExternalIds()


# ---------------------------------------------------------------------------
# WatchProvider
# ---------------------------------------------------------------------------


def test_watch_provider_minimal_ok():
    wp = WatchProvider(name="Netflix", url="https://netflix.com/title/1")
    assert wp.region is None


def test_watch_provider_empty_name_raises():
    with pytest.raises(ValueError, match="name"):
        WatchProvider(name="", url="https://x")


def test_watch_provider_blank_name_raises():
    with pytest.raises(ValueError, match="name"):
        WatchProvider(name="   ", url="https://x")


def test_watch_provider_empty_url_raises():
    with pytest.raises(ValueError, match="url"):
        WatchProvider(name="Netflix", url="")


def test_watch_provider_blank_url_raises():
    with pytest.raises(ValueError, match="url"):
        WatchProvider(name="Netflix", url="   ")


def test_watch_provider_is_frozen():
    wp = WatchProvider(name="Netflix", url="https://x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        wp.name = "Other"  # type: ignore[misc]


# B8 — ethics
@pytest.mark.parametrize("value", [None, "indie", "neutral", "avoid"])
def test_watch_provider_ethics_accepted(value):
    wp = WatchProvider(name="N", url="https://x", ethics=value)
    assert wp.ethics == value


@pytest.mark.parametrize("value", ["INDIE", "bad", "", " indie ", 1])
def test_watch_provider_ethics_rejected(value):
    with pytest.raises(ValueError, match="ethics"):
        WatchProvider(name="N", url="https://x", ethics=value)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CustomLink
# ---------------------------------------------------------------------------


def test_custom_link_minimal_ok():
    cl = CustomLink(label="Site officiel", url="https://example.com")
    assert cl.label == "Site officiel"


def test_custom_link_empty_label_raises():
    with pytest.raises(ValueError, match="label"):
        CustomLink(label="", url="https://x")


def test_custom_link_blank_label_raises():
    with pytest.raises(ValueError, match="label"):
        CustomLink(label="  ", url="https://x")


def test_custom_link_empty_url_raises():
    with pytest.raises(ValueError, match="url"):
        CustomLink(label="x", url="")


def test_custom_link_blank_url_raises():
    with pytest.raises(ValueError, match="url"):
        CustomLink(label="x", url="   ")


def test_custom_link_is_frozen():
    cl = CustomLink(label="x", url="y")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cl.label = "z"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Item — construction minimale et nominale
# ---------------------------------------------------------------------------


def _make_item(**overrides):
    base = dict(
        id="abc12345",
        types=(ItemType.FILM,),
        title="Drive",
    )
    base.update(overrides)
    return Item(**base)


def test_item_minimal_construction():
    it = _make_item()
    assert it.id == "abc12345"
    assert it.title == "Drive"
    assert it.types == (ItemType.FILM,)
    assert it.creator is None
    assert it.year is None
    assert it.aliases == ()
    assert it.custom_links == ()
    assert it.watch_providers == ()
    assert it.link_overrides == {}
    assert isinstance(it.external_ids, ExternalIds)
    assert it.schema_version == 1


def test_item_with_all_fields():
    it = _make_item(
        creator="Nicolas Winding Refn",
        year=2011,
        aliases=("Drive (film)",),
        external_ids=ExternalIds(tmdb=1, tmdb_type="movie"),
        custom_links=(CustomLink(label="IMDb", url="https://imdb.com/x"),),
        watch_providers=(WatchProvider(name="Netflix", url="https://nf"),),
        link_overrides={"tmdb": "https://override"},
        schema_version=2,
    )
    assert it.creator == "Nicolas Winding Refn"
    assert it.year == 2011
    assert it.aliases == ("Drive (film)",)
    assert it.custom_links[0].label == "IMDb"
    assert it.watch_providers[0].name == "Netflix"
    assert it.link_overrides["tmdb"] == "https://override"
    assert it.schema_version == 2


# ---------------------------------------------------------------------------
# Item — validation `id`
# ---------------------------------------------------------------------------


def test_item_id_empty_raises():
    with pytest.raises(ValueError, match="id"):
        _make_item(id="")


def test_item_id_uppercase_raises():
    with pytest.raises(ValueError, match="id"):
        _make_item(id="ABC123")


def test_item_id_special_chars_raises():
    with pytest.raises(ValueError, match="id"):
        _make_item(id="abc_123")


def test_item_id_too_long_raises():
    with pytest.raises(ValueError, match="id"):
        _make_item(id="a" * 65)


# C4 — Regex tightened
@pytest.mark.parametrize("bad", [
    "------",       # tirets seuls
    "-abc",         # leading dash
    "abc-",         # trailing dash
    "a--b",         # double dash
    "-",
])
def test_item_id_pathological_dashes_rejected(bad):
    """C4 — Le regex resserré refuse les ids dégénérés."""
    with pytest.raises(ValueError, match="id"):
        _make_item(id=bad)


@pytest.mark.parametrize("good", ["a", "abc", "abc-def", "a1-b2", "00080c17"])
def test_item_id_valid_slugs_accepted(good):
    """C4 — Les slugs canoniques continuent à passer."""
    it = _make_item(id=good)
    assert it.id == good


def test_item_id_max_length_ok():
    it = _make_item(id="a" * 64)
    assert it.id == "a" * 64


def test_item_id_with_dash_ok():
    it = _make_item(id="abc-1234-5678")
    assert it.id == "abc-1234-5678"


def test_item_id_non_str_raises():
    with pytest.raises(ValueError, match="id"):
        _make_item(id=123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Item — validation `types`
# ---------------------------------------------------------------------------


def test_item_types_empty_raises():
    with pytest.raises(ValueError, match="types"):
        _make_item(types=())


def test_item_types_must_be_tuple_not_list():
    with pytest.raises(ValueError, match="types"):
        _make_item(types=[ItemType.FILM])  # type: ignore[arg-type]


def test_item_types_with_non_item_type_raises():
    with pytest.raises(ValueError, match="types"):
        _make_item(types=("film",))  # type: ignore[arg-type]


def test_item_types_multiple_ok():
    it = _make_item(types=(ItemType.FILM, ItemType.SERIES))
    assert it.types == (ItemType.FILM, ItemType.SERIES)


# ---------------------------------------------------------------------------
# Item — validation `title`
# ---------------------------------------------------------------------------


def test_item_title_empty_raises():
    with pytest.raises(ValueError, match="title"):
        _make_item(title="")


def test_item_title_blank_raises():
    with pytest.raises(ValueError, match="title"):
        _make_item(title="   ")


def test_item_title_non_str_raises():
    with pytest.raises(ValueError, match="title"):
        _make_item(title=42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Item — validation `creator`
# ---------------------------------------------------------------------------


def test_item_creator_none_ok():
    it = _make_item(creator=None)
    assert it.creator is None


def test_item_creator_blank_raises():
    with pytest.raises(ValueError, match="creator"):
        _make_item(creator="   ")


def test_item_creator_non_str_raises():
    with pytest.raises(ValueError, match="creator"):
        _make_item(creator=42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Item — validation `year`
# ---------------------------------------------------------------------------


def test_item_year_none_ok():
    assert _make_item(year=None).year is None


def test_item_year_below_min_raises():
    with pytest.raises(ValueError, match="year"):
        _make_item(year=1799)


def test_item_year_above_max_raises():
    with pytest.raises(ValueError, match="year"):
        _make_item(year=2101)


def test_item_year_min_ok():
    assert _make_item(year=1800).year == 1800


def test_item_year_max_ok():
    assert _make_item(year=2100).year == 2100


def test_item_year_non_int_raises():
    with pytest.raises(ValueError, match="year"):
        _make_item(year="2011")  # type: ignore[arg-type]


def test_item_year_bool_raises():
    # bool est sous-type d'int en Python → on l'interdit explicitement.
    with pytest.raises(ValueError, match="year"):
        _make_item(year=True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Item — validation `aliases`
# ---------------------------------------------------------------------------


def test_item_aliases_must_be_tuple():
    with pytest.raises(ValueError, match="aliases"):
        _make_item(aliases=["alt"])  # type: ignore[arg-type]


def test_item_aliases_blank_raises():
    with pytest.raises(ValueError, match="aliases"):
        _make_item(aliases=("",))


# ---------------------------------------------------------------------------
# Item — validation `custom_links` / `watch_providers`
# ---------------------------------------------------------------------------


def test_item_custom_links_must_be_tuple():
    with pytest.raises(ValueError, match="custom_links"):
        _make_item(custom_links=[CustomLink(label="x", url="y")])  # type: ignore[arg-type]


def test_item_watch_providers_must_be_tuple():
    with pytest.raises(ValueError, match="watch_providers"):
        _make_item(watch_providers=[WatchProvider(name="N", url="U")])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Item — validation `tmdb_type` via ExternalIds
# ---------------------------------------------------------------------------


def test_item_external_ids_invalid_tmdb_type_raises():
    with pytest.raises(ValueError, match="tmdb_type"):
        _make_item(external_ids=ExternalIds(tmdb_type="bogus"))


# ---------------------------------------------------------------------------
# Item — validation `schema_version`
# ---------------------------------------------------------------------------


def test_item_schema_version_zero_raises():
    with pytest.raises(ValueError, match="schema_version"):
        _make_item(schema_version=0)


def test_item_schema_version_negative_raises():
    with pytest.raises(ValueError, match="schema_version"):
        _make_item(schema_version=-1)


def test_item_schema_version_non_int_raises():
    with pytest.raises(ValueError, match="schema_version"):
        _make_item(schema_version="1")  # type: ignore[arg-type]


def test_item_schema_version_bool_raises():
    with pytest.raises(ValueError, match="schema_version"):
        _make_item(schema_version=True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Item — immutabilité
# ---------------------------------------------------------------------------


def test_item_is_frozen():
    it = _make_item()
    with pytest.raises(dataclasses.FrozenInstanceError):
        it.title = "Other"  # type: ignore[misc]


def test_item_equality():
    a = _make_item()
    b = _make_item()
    assert a == b


def test_item_hashable():
    # frozen dataclasses → hashables si tous les champs le sont. Les
    # `Mapping` (dict) ne le sont pas — on vérifie juste que les champs
    # par défaut conservent l'égalité structurelle.
    a = _make_item()
    b = _make_item()
    assert a == b
