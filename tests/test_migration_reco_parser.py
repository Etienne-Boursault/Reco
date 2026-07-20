"""Tests de `tools.repository.migration.reco_parser` — conversion pure.

Couverture cible : 100%. Zéro IO (pas de `tmp_path`).
"""
from __future__ import annotations

import pytest

from domain.item import ItemType
from domain.mention import (
    MentionKind,
    MentionStatus,
    TranscriptSource,
)
from domain.services.identity import canonical_key
from repository.migration.reco_parser import reco_dict_to_item_mention


# ---------------------------------------------------------------------------
# Resolvers de test
# ---------------------------------------------------------------------------


def _fixed_resolver(id_: str = "abc12345"):
    """Resolver qui renvoie toujours `id_`."""

    def _r(_canon, _creator, _types):
        return id_

    return _r


def _tracking_resolver():
    """Resolver qui enregistre les appels et renvoie un id stable par canonical."""
    calls: list[tuple[str, str | None, tuple[ItemType, ...]]] = []
    seen: dict[str, str] = {}

    def _r(canonical, creator, types):
        calls.append((canonical, creator, types))
        if canonical not in seen:
            seen[canonical] = f"id-{len(seen):08x}"
        return seen[canonical]

    return _r, calls


# ---------------------------------------------------------------------------
# Cas nominaux
# ---------------------------------------------------------------------------


def test_minimal_reco_parses_to_item_and_mention():
    reco = {
        "id": "ubm-0001",
        "sourceId": "un-bon-moment",
        "title": "Titanic",
        "types": ["film"],
    }
    item, mention = reco_dict_to_item_mention(
        reco, item_id_resolver=_fixed_resolver("abc12345"),
    )
    assert item.id == "abc12345"
    assert item.title == "Titanic"
    assert item.types == (ItemType.FILM,)
    assert item.creator is None
    assert mention.id == "ubm-0001"
    assert mention.item_id == "abc12345"
    assert mention.source_ref.source_id == "un-bon-moment"
    assert mention.kind == MentionKind.RECO
    assert mention.status == MentionStatus.DRAFT


def test_reco_with_all_optional_fields_preserved():
    reco = {
        "id": "ubm-c01",
        "sourceId": "un-bon-moment",
        "title": "Mortel",
        "creator": "Inconnu",
        "types": ["serie"],
        "episodeGuid": "ep-guid",
        "timestamp": "00:13:21",
        "transcriptSource": "youtube",
        "status": "validated",
        "kind": "reco",
        "recommendedBy": "Hakim",
        "quote": "j'ai kiffé",
        "externalIds": {"tmdb": 94801, "tmdbType": "tv"},
        "extractors": ["anthropic"],
        "watchProviders": [
            {"label": "Netflix", "url": "https://nflx.example/x"},
        ],
        "customLinks": [
            {"label": "site", "url": "https://example.com"},
        ],
        "linkOverrides": {"x": "https://x.example/y"},
        "aliases": ["Mortel FR"],
    }
    item, mention = reco_dict_to_item_mention(
        reco, item_id_resolver=_fixed_resolver(),
    )
    assert item.external_ids.tmdb == 94801
    assert item.external_ids.tmdb_type == "tv"
    assert item.watch_providers[0].name == "Netflix"
    assert item.custom_links[0].label == "site"
    assert dict(item.link_overrides) == {"x": "https://x.example/y"}
    assert item.aliases == ("Mortel FR",)
    assert mention.source_ref.transcript_source == TranscriptSource.YOUTUBE
    assert mention.source_ref.timestamp == "00:13:21"
    assert mention.status == MentionStatus.VALIDATED
    assert mention.recommended_by == "Hakim"
    assert mention.quote == "j'ai kiffé"
    assert mention.extractors == ("anthropic",)


def test_reco_id_becomes_mention_id():
    reco = {
        "id": "preserve-me-99",
        "sourceId": "x",
        "title": "T",
        "types": ["film"],
    }
    _item, mention = reco_dict_to_item_mention(
        reco, item_id_resolver=_fixed_resolver(),
    )
    assert mention.id == "preserve-me-99"


def test_item_id_derived_via_resolver_with_canonical():
    reco = {
        "id": "ubm-1",
        "sourceId": "x",
        "title": "Hello World",
        "creator": "Alice",
        "types": ["film"],
    }
    resolver, calls = _tracking_resolver()
    item, _mention = reco_dict_to_item_mention(reco, item_id_resolver=resolver)
    assert len(calls) == 1
    passed_canon, passed_creator, passed_types = calls[0]
    assert passed_canon == canonical_key("Hello World", "Alice")
    assert passed_creator == "Alice"
    assert passed_types == (ItemType.FILM,)
    # L'id retourné par le resolver est bien utilisé.
    assert item.id == "id-00000000"


# ---------------------------------------------------------------------------
# Statuses / kinds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status_str,expected", [
    ("draft", MentionStatus.DRAFT),
    ("validated", MentionStatus.VALIDATED),
    ("discarded", MentionStatus.DISCARDED),
])
def test_reco_status_preserved(status_str, expected):
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "types": ["film"], "status": status_str,
    }
    _i, m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert m.status == expected


def test_reco_kind_citation_preserved():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "types": ["film"], "kind": "citation",
    }
    _i, m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert m.kind == MentionKind.CITATION


def test_reco_no_kind_defaults_to_reco():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
    }
    _i, m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert m.kind == MentionKind.RECO


def test_invalid_status_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "types": ["film"], "status": "bogus",
    }
    with pytest.raises(ValueError, match="status"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_invalid_kind_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "types": ["film"], "kind": "bogus",
    }
    with pytest.raises(ValueError, match="kind"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_invalid_kind_type_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "types": ["film"], "kind": 42,
    }
    with pytest.raises(ValueError, match="kind"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_invalid_status_type_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "types": ["film"], "status": 99,
    }
    with pytest.raises(ValueError, match="status"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


# ---------------------------------------------------------------------------
# Extraction history round-trip
# ---------------------------------------------------------------------------


def test_extraction_history_round_trip():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "extractionHistory": [
            {
                "at": "2026-06-06T00:21:25+00:00",
                "llmModel": "claude-haiku-4-5",
                "llmProvider": "anthropic",
                "transcriptModel": "large-v3",
                "transcriptSource": "youtube",
                "worker": "main-cpu",
                "timestamp_at_extraction": "00:58:15",
            }
        ],
    }
    _i, m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert len(m.extraction_history) == 1
    e = m.extraction_history[0]
    assert e.llm_provider == "anthropic"
    assert e.llm_model == "claude-haiku-4-5"
    assert e.transcript_source == TranscriptSource.YOUTUBE
    assert e.worker == "main-cpu"
    assert e.extra["timestamp_at_extraction"] == "00:58:15"


def test_extraction_history_invalid_entry_type():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "extractionHistory": ["not-a-dict"],
    }
    with pytest.raises(ValueError, match="extractionHistory"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_extraction_history_not_list():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "extractionHistory": {"not": "a list"},
    }
    with pytest.raises(ValueError, match="extractionHistory"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


# ---------------------------------------------------------------------------
# External IDs
# ---------------------------------------------------------------------------


def test_external_ids_round_trip_string_tmdb_coerced_to_int():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": {"tmdb": "12345", "tmdbType": "movie"},
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.external_ids.tmdb == 12345
    assert i.external_ids.tmdb_type == "movie"


def test_external_ids_tmdb_int_preserved():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": {"tmdb": 42},
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.external_ids.tmdb == 42


def test_external_ids_tmdb_bool_rejected():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": {"tmdb": True},
    }
    with pytest.raises(ValueError, match="tmdb"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_external_ids_tmdb_non_numeric_string_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": {"tmdb": "abc"},
    }
    with pytest.raises(ValueError, match="tmdb"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_external_ids_tmdb_invalid_type():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": {"tmdb": []},
    }
    with pytest.raises(ValueError, match="tmdb"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_external_ids_invalid_tmdb_type_silently_dropped():
    """Si `tmdbType` invalide, on le drop (silently) plutôt que de bloquer."""
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": {"tmdbType": "bogus"},
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.external_ids.tmdb_type is None


def test_external_ids_none_returns_empty():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": None,
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.external_ids.tmdb is None


def test_external_ids_not_mapping_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": ["not-a-dict"],
    }
    with pytest.raises(ValueError, match="externalIds"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_external_ids_tmdb_empty_string_treated_as_invalid():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": {"tmdb": "   "},
    }
    with pytest.raises(ValueError, match="tmdb"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


# ---------------------------------------------------------------------------
# Types legacy (ADR 0006: spectacle/lieu/video préservés tels quels)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "legacy_type,expected",
    [
        ("spectacle", ItemType.SHOW),
        ("lieu", ItemType.PLACE),
        ("video", ItemType.VIDEO),
    ],
)
def test_legacy_types_preserved(legacy_type, expected):
    """ADR 0006 : les types historiques `spectacle/lieu/video` sont
    désormais des valeurs first-class dans `ItemType` (plus d'écrasement
    silencieux vers OTHER)."""
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "types": [legacy_type],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.types == (expected,)


def test_unknown_type_raises_clear_error():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "types": ["this-does-not-exist"],
    }
    with pytest.raises(ValueError, match="this-does-not-exist"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_types_dedup_preserves_order():
    """Dédoublonnage : types distincts conservent l'ordre d'apparition."""
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "types": ["spectacle", "spectacle", "film"],  # → SHOW (dup ignoré), FILM
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.types == (ItemType.SHOW, ItemType.FILM)


def test_types_empty_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": [],
    }
    with pytest.raises(ValueError, match="types"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_types_not_list_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": "film",
    }
    with pytest.raises(ValueError, match="types"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_types_non_str_element_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": [42],
    }
    with pytest.raises(ValueError, match="non-str"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


# ---------------------------------------------------------------------------
# Collections — coercions et validations
# ---------------------------------------------------------------------------


def test_watch_providers_label_aliased_to_name():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "watchProviders": [
            {"label": "Netflix", "url": "https://nflx.example/y", "ethics": "neutral"},
        ],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.watch_providers[0].name == "Netflix"


def test_watch_providers_missing_url_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "watchProviders": [{"label": "Netflix"}],
    }
    with pytest.raises(ValueError, match="watchProvider"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_watch_providers_entry_not_mapping():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "watchProviders": ["not-a-dict"],
    }
    with pytest.raises(ValueError, match="watchProvider"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_watch_providers_not_list():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "watchProviders": {"not": "list"},
    }
    with pytest.raises(ValueError, match="watchProviders"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_watch_providers_with_name_preferred_over_label():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "watchProviders": [
            {"name": "Disney+", "label": "ignore-me", "url": "https://d.example/y"},
        ],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.watch_providers[0].name == "Disney+"


def test_custom_links_round_trip():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "customLinks": [{"label": "site", "url": "https://example.com/x"}],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.custom_links[0].label == "site"


def test_custom_links_entry_missing_url():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "customLinks": [{"label": "site"}],
    }
    with pytest.raises(ValueError, match="customLink"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_custom_links_entry_not_mapping():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "customLinks": ["bogus"],
    }
    with pytest.raises(ValueError, match="customLink"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_custom_links_not_list():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "customLinks": "bogus",
    }
    with pytest.raises(ValueError, match="customLinks"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_link_overrides_round_trip():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "linkOverrides": {"k": "https://v.example/x"},
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert dict(i.link_overrides) == {"k": "https://v.example/x"}


def test_link_overrides_not_mapping():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "linkOverrides": ["bogus"],
    }
    with pytest.raises(ValueError, match="linkOverrides"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_link_overrides_non_str_value():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "linkOverrides": {"k": 42},
    }
    with pytest.raises(ValueError, match="linkOverrides"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_aliases_not_list():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "aliases": "bogus",
    }
    with pytest.raises(ValueError, match="aliases"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_aliases_invalid_entry():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "aliases": [""],
    }
    with pytest.raises(ValueError, match="alias"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_extractors_not_list():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "extractors": "bogus",
    }
    with pytest.raises(ValueError, match="extractors"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_extractors_invalid_entry():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "extractors": [""],
    }
    with pytest.raises(ValueError, match="extractor"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


# ---------------------------------------------------------------------------
# Required field validation
# ---------------------------------------------------------------------------


def test_invalid_reco_not_mapping():
    with pytest.raises(ValueError, match="reco doit"):
        reco_dict_to_item_mention("nope", item_id_resolver=_fixed_resolver())  # type: ignore[arg-type]


@pytest.mark.parametrize("missing", ["id", "title", "sourceId"])
def test_missing_required_field_raises(missing):
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
    }
    del reco[missing]
    with pytest.raises(ValueError, match="champ requis"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_blank_id_raises():
    reco = {"id": "  ", "sourceId": "x", "title": "T", "types": ["film"]}
    with pytest.raises(ValueError, match="id"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_blank_title_raises():
    reco = {"id": "x-1", "sourceId": "x", "title": "  ", "types": ["film"]}
    with pytest.raises(ValueError, match="title"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_blank_source_id_raises():
    reco = {"id": "x-1", "sourceId": "  ", "title": "T", "types": ["film"]}
    with pytest.raises(ValueError, match="sourceId"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_non_str_id_raises():
    reco = {"id": 42, "sourceId": "x", "title": "T", "types": ["film"]}
    with pytest.raises(ValueError, match="id"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_non_str_title_raises():
    reco = {"id": "x-1", "sourceId": "x", "title": 42, "types": ["film"]}
    with pytest.raises(ValueError, match="title"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_non_str_source_id_raises():
    reco = {"id": "x-1", "sourceId": 99, "title": "T", "types": ["film"]}
    with pytest.raises(ValueError, match="sourceId"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


# ---------------------------------------------------------------------------
# Creator
# ---------------------------------------------------------------------------


def test_creator_empty_string_normalised_to_none():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "creator": "  ", "types": ["film"],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.creator is None


def test_creator_none_kept_none():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "creator": None, "types": ["film"],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.creator is None


def test_creator_invalid_type_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T",
        "creator": 42, "types": ["film"],
    }
    with pytest.raises(ValueError, match="creator"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


# ---------------------------------------------------------------------------
# Transcript source
# ---------------------------------------------------------------------------


def test_invalid_transcript_source_raises():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "transcriptSource": "bogus",
    }
    with pytest.raises(ValueError, match="transcriptSource"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_invalid_transcript_source_type():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "transcriptSource": 42,
    }
    with pytest.raises(ValueError, match="transcriptSource"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_transcript_source_already_enum_passes_through():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "transcriptSource": TranscriptSource.ACAST,
    }
    _i, m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert m.source_ref.transcript_source == TranscriptSource.ACAST


def test_kind_already_enum_passes_through():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "kind": MentionKind.CITATION,
    }
    _i, m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert m.kind == MentionKind.CITATION


def test_status_already_enum_passes_through():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "status": MentionStatus.VALIDATED,
    }
    _i, m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert m.status == MentionStatus.VALIDATED


# ---------------------------------------------------------------------------
# A5 — Normalisation timestamp legacy MM:SS
# ---------------------------------------------------------------------------


def test_normalize_timestamp_mmss_to_hhmmss():
    from repository.migration.reco_parser import _normalize_timestamp
    assert _normalize_timestamp("12:34") == "00:12:34"


def test_normalize_timestamp_single_digit_minute_padded():
    from repository.migration.reco_parser import _normalize_timestamp
    assert _normalize_timestamp("5:30") == "00:05:30"


def test_normalize_timestamp_hhmmss_unchanged():
    from repository.migration.reco_parser import _normalize_timestamp
    assert _normalize_timestamp("01:23:45") == "01:23:45"


def test_normalize_timestamp_none_returns_none():
    from repository.migration.reco_parser import _normalize_timestamp
    assert _normalize_timestamp(None) is None


def test_normalize_timestamp_empty_returns_none():
    from repository.migration.reco_parser import _normalize_timestamp
    assert _normalize_timestamp("  ") is None


def test_normalize_timestamp_invalid_passes_through():
    """Format inconnu : laissé tel quel, le domain SourceRef rejettera."""
    from repository.migration.reco_parser import _normalize_timestamp
    assert _normalize_timestamp("not-a-timestamp") == "not-a-timestamp"


def test_normalize_timestamp_non_str_passes_through():
    """Type non-str : passe tel quel pour laisser le domain rejeter."""
    from repository.migration.reco_parser import _normalize_timestamp
    assert _normalize_timestamp(123) == 123  # type: ignore[arg-type]


def test_parser_applies_normalize_to_source_ref():
    """Le parser convertit MM:SS legacy en HH:MM:SS quand il construit SourceRef."""
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "timestamp": "12:34",
    }
    _i, m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert m.source_ref.timestamp == "00:12:34"


# ---------------------------------------------------------------------------
# year normalization (str → int, hors bornes → None)
# ---------------------------------------------------------------------------


def test_year_str_coerced_to_int():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "year": "2020",
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.year == 2020


def test_year_out_of_range_normalized_to_none():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "year": 1500,
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.year is None


def test_year_invalid_str_normalized_to_none():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "year": "not-a-year",
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.year is None


def test_year_bool_normalized_to_none():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "year": True,
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.year is None


def test_year_none_passes_through():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.year is None


def test_year_int_in_range_kept():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "year": 1999,
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.year == 1999


def test_year_empty_string_normalized_to_none():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "year": "",
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.year is None


def test_year_float_normalized_to_none():
    """Un float comme valeur de year (cas pathologique legacy) → None."""
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "year": 2020.5,
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.year is None


# ---------------------------------------------------------------------------
# B8 — WatchProvider.ethics round-trip
# ---------------------------------------------------------------------------


def test_watch_providers_ethics_round_trip():
    """Le champ `ethics` (`indie`/`neutral`/`avoid`) est préservé depuis legacy."""
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "watchProviders": [
            {"name": "Netflix", "url": "https://nflx.example/x", "ethics": "neutral"},
            {"name": "Indie+", "url": "https://i.example/x", "ethics": "indie"},
        ],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.watch_providers[0].ethics == "neutral"
    assert i.watch_providers[1].ethics == "indie"


def test_watch_providers_ethics_absent_is_none():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "watchProviders": [{"name": "X", "url": "https://x.example/y"}],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.watch_providers[0].ethics is None


# ---------------------------------------------------------------------------
# B9 — aliases strip cohérent
# ---------------------------------------------------------------------------


def test_aliases_with_whitespace_stripped():
    """Les alias sont strip-és (whitespace en bordures retiré)."""
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "aliases": ["  Mortel FR  ", "Mortel US"],
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.aliases == ("Mortel FR", "Mortel US")


# ---------------------------------------------------------------------------
# B10 — extractionHistory.llmProvider / llmModel manquant ou vide
# ---------------------------------------------------------------------------


def test_extraction_history_missing_llmProvider_raises_with_context():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "extractionHistory": [
            {"llmModel": "claude-haiku-4-5", "at": "2026-06-06T00:00:00+00:00"},
        ],
    }
    with pytest.raises(ValueError, match="llmProvider"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_extraction_history_empty_llmProvider_raises_with_context():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "extractionHistory": [
            {
                "llmProvider": "",
                "llmModel": "claude-haiku-4-5",
                "at": "2026-06-06T00:00:00+00:00",
            },
        ],
    }
    with pytest.raises(ValueError, match="llmProvider"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_extraction_history_missing_llmModel_raises_with_context():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "extractionHistory": [
            {"llmProvider": "anthropic", "at": "2026-06-06T00:00:00+00:00"},
        ],
    }
    with pytest.raises(ValueError, match="llmModel"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


def test_extraction_history_missing_at_raises_with_context():
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "extractionHistory": [
            {"llmProvider": "anthropic", "llmModel": "claude-haiku-4-5"},
        ],
    }
    with pytest.raises(ValueError, match="at"):
        reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())


# ---------------------------------------------------------------------------
# C10 — _parse_external_ids délègue à ExternalIds.from_partial
# ---------------------------------------------------------------------------


def test_external_ids_invalid_tmdb_type_silently_dropped_via_factory():
    """Même politique qu'avant la refacto : tmdbType inconnu → None."""
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": {"tmdb": 1, "tmdbType": "blu-ray"},
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.external_ids.tmdb == 1
    assert i.external_ids.tmdb_type is None


def test_external_ids_partial_payload_uses_factory():
    """Un dict partial (que des None / champs absents) → ExternalIds vide."""
    reco = {
        "id": "x-1", "sourceId": "x", "title": "T", "types": ["film"],
        "externalIds": {"spotify": "spX"},
    }
    i, _m = reco_dict_to_item_mention(reco, item_id_resolver=_fixed_resolver())
    assert i.external_ids.tmdb is None
    assert i.external_ids.spotify == "spX"
