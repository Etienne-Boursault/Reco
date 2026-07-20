"""Tests du schéma `SourceConfig` (couche domaine pure, sans I/O).

TDD strict — ces tests pilotent la définition de `tools/config/schema.py`.
"""

from __future__ import annotations

import dataclasses

import pytest

from tools.config.schema import SourceConfig


# ---------------------------------------------------------------------------
# Construction minimale & défauts
# ---------------------------------------------------------------------------


def _minimal_kwargs(**overrides):
    """Renvoie le kit minimum requis pour instancier `SourceConfig`."""
    base = {
        "id": "un-bon-moment",
        "title": "Un Bon Moment",
        "reco_prefix": "ubm",
        "hosts": ("Kyan", "Navo"),
    }
    base.update(overrides)
    return base


def test_minimal_config_has_required_fields_only():
    """Un minimum d'infos suffit à instancier (id/title/reco_prefix/hosts)."""
    cfg = SourceConfig(**_minimal_kwargs())
    assert cfg.id == "un-bon-moment"
    assert cfg.title == "Un Bon Moment"
    assert cfg.reco_prefix == "ubm"
    assert cfg.hosts == ("Kyan", "Navo")


def test_optional_fields_have_defaults():
    """Les champs optionnels ont des défauts utilisables sans config."""
    cfg = SourceConfig(**_minimal_kwargs())
    assert cfg.description == ""
    assert cfg.rss_url is None
    assert cfg.youtube_channel_url is None
    assert cfg.spotify_show_id is None
    assert cfg.transcript_default_source == "youtube"
    assert cfg.site_color_accent == "#ffd23f"
    assert cfg.site_url is None
    # Politique projet déplacée dans tools.config.policies — défaut schéma = ().
    assert cfg.avoid_brands == ()
    assert cfg.extraction_anchor_patterns == ()
    assert cfg.youtube_title_suffix_patterns == ()
    assert cfg.enabled is True
    assert cfg.schema_version == 1
    assert dict(cfg.extra) == {}


# ---------------------------------------------------------------------------
# Immutabilité (DIP : pas de mutation après injection)
# ---------------------------------------------------------------------------


def test_frozen_immutable():
    """`frozen=True` empêche toute mutation (cf. DIP — injection par valeur)."""
    cfg = SourceConfig(**_minimal_kwargs())
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.title = "autre"  # type: ignore[misc]


def test_hosts_tuple_not_list():
    """`hosts` doit être un tuple (immutable) — refuse les listes."""
    with pytest.raises(TypeError, match="hosts.*tuple"):
        SourceConfig(**_minimal_kwargs(hosts=["Kyan", "Navo"]))  # type: ignore[arg-type]


def test_avoid_brands_tuple_not_list():
    """Idem pour `avoid_brands`."""
    with pytest.raises(TypeError, match="avoid_brands.*tuple"):
        SourceConfig(**_minimal_kwargs(avoid_brands=["X"]))  # type: ignore[arg-type]


def test_extraction_anchor_patterns_tuple_not_list():
    with pytest.raises(TypeError, match="extraction_anchor_patterns.*tuple"):
        SourceConfig(
            **_minimal_kwargs(extraction_anchor_patterns=["pattern"])  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Validation des champs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_id", ["", "Un Bon Moment", "with space", "UPPER", "id!"])
def test_id_format_rejects_invalid(bad_id):
    """L'id doit être un slug [a-z0-9-]+ (refuse espaces/majuscules/ponctuation)."""
    with pytest.raises(ValueError, match="id"):
        SourceConfig(**_minimal_kwargs(id=bad_id))


@pytest.mark.parametrize("ok_id", ["a", "x-y", "un-bon-moment", "show-2024"])
def test_id_format_accepts_valid(ok_id):
    cfg = SourceConfig(**_minimal_kwargs(id=ok_id))
    assert cfg.id == ok_id


@pytest.mark.parametrize(
    "bad_prefix",
    ["", "ub m", "UB", "ub!", "ub-", "x", "toolongprefix"],
)
def test_invalid_prefix_raises(bad_prefix):
    """Le préfixe doit être [a-z0-9]{2,8} (pas d'espaces/tirets/majuscules,
    2-8 chars). Cf. issue #35."""
    with pytest.raises(ValueError, match="reco_prefix"):
        SourceConfig(**_minimal_kwargs(reco_prefix=bad_prefix))


def test_invalid_title_raises():
    with pytest.raises(ValueError, match="title"):
        SourceConfig(**_minimal_kwargs(title=""))


def test_invalid_hosts_empty_raises():
    """Au moins un hôte requis (autrement le prompt LLM perd un repère)."""
    with pytest.raises(ValueError, match="hosts"):
        SourceConfig(**_minimal_kwargs(hosts=()))


def test_invalid_transcript_default_source_raises():
    with pytest.raises(ValueError, match="transcript_default_source"):
        SourceConfig(**_minimal_kwargs(transcript_default_source="acastoid"))


@pytest.mark.parametrize("ok", ["youtube", "acast"])
def test_valid_transcript_default_source(ok):
    cfg = SourceConfig(**_minimal_kwargs(transcript_default_source=ok))
    assert cfg.transcript_default_source == ok


# ---------------------------------------------------------------------------
# Helpers d'instanciation
# ---------------------------------------------------------------------------


def test_from_dict_roundtrip():
    """`from_dict` accepte un payload JSON-like et reconstitue la config."""
    payload = {
        "id": "un-bon-moment",
        "title": "Un Bon Moment",
        "description": "desc",
        "reco_prefix": "ubm",
        "hosts": ["Kyan", "Navo"],  # listes JSON → tuple en interne
        "rss_url": "https://example.com/feed",
        "youtube_channel_url": "https://youtube.com/@x",
        "extraction_anchor_patterns": ["est-ce que tu as une reco"],
        "avoid_brands": ["Amazon"],
        "site_color_accent": "#000000",
    }
    cfg = SourceConfig.from_dict(payload)
    assert cfg.id == "un-bon-moment"
    assert cfg.hosts == ("Kyan", "Navo")
    assert cfg.extraction_anchor_patterns == ("est-ce que tu as une reco",)
    assert cfg.avoid_brands == ("Amazon",)


def test_from_dict_missing_required_raises():
    with pytest.raises(ValueError, match="requis|manquants"):
        SourceConfig.from_dict({"id": "x"})  # title manquant


# ---------------------------------------------------------------------------
# Validation de types stricts (issue #3)
# ---------------------------------------------------------------------------


def test_description_null_normalized_to_empty_string():
    """Un payload Astro peut omettre `description` (= null en JSON).
    Le schéma exige `str` — `from_dict` doit normaliser None → ""."""
    cfg = SourceConfig.from_dict(
        {
            "id": "x", "title": "X", "reco_prefix": "xx",
            "hosts": ["A"], "description": None,
        },
    )
    assert cfg.description == ""


def test_rss_url_non_string_raises():
    with pytest.raises(TypeError, match="rss_url"):
        SourceConfig(**_minimal_kwargs(rss_url=42))  # type: ignore[arg-type]


def test_hosts_with_non_string_raises():
    with pytest.raises(TypeError, match="hosts"):
        SourceConfig(**_minimal_kwargs(hosts=("A", 42)))  # type: ignore[arg-type]


def test_avoid_brands_with_non_string_raises():
    with pytest.raises(TypeError, match="avoid_brands"):
        SourceConfig(**_minimal_kwargs(avoid_brands=("Amazon", 42)))  # type: ignore[arg-type]


def test_extraction_anchor_patterns_with_non_string_raises():
    with pytest.raises(TypeError, match="extraction_anchor_patterns"):
        SourceConfig(
            **_minimal_kwargs(extraction_anchor_patterns=("ok", 42))  # type: ignore[arg-type]
        )


def test_youtube_title_suffix_patterns_tuple_not_list():
    with pytest.raises(TypeError, match="youtube_title_suffix_patterns"):
        SourceConfig(
            **_minimal_kwargs(youtube_title_suffix_patterns=["x"])  # type: ignore[arg-type]
        )


def test_enabled_non_bool_raises():
    with pytest.raises(TypeError, match="enabled"):
        SourceConfig(**_minimal_kwargs(enabled="yes"))  # type: ignore[arg-type]


def test_schema_version_non_int_raises():
    with pytest.raises(TypeError, match="schema_version"):
        SourceConfig(**_minimal_kwargs(schema_version="1"))  # type: ignore[arg-type]


def test_title_non_string_raises():
    with pytest.raises(TypeError, match="title"):
        SourceConfig(**_minimal_kwargs(title=42))  # type: ignore[arg-type]


def test_description_non_string_raises():
    with pytest.raises(TypeError, match="description"):
        SourceConfig(**_minimal_kwargs(description=42))  # type: ignore[arg-type]


def test_id_non_string_raises():
    with pytest.raises(TypeError, match="id"):
        SourceConfig(**_minimal_kwargs(id=42))  # type: ignore[arg-type]


def test_reco_prefix_non_string_raises():
    with pytest.raises(TypeError, match="reco_prefix"):
        SourceConfig(**_minimal_kwargs(reco_prefix=42))  # type: ignore[arg-type]


def test_youtube_title_suffix_patterns_with_non_string_raises():
    with pytest.raises(TypeError, match="youtube_title_suffix_patterns"):
        SourceConfig(
            **_minimal_kwargs(youtube_title_suffix_patterns=("ok", 42))  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Validation hex `site_color_accent` (issue #32)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "fff", "#ff", "#GGGGGG", "blue", "#ffff"])
def test_site_color_accent_invalid_raises(bad):
    with pytest.raises(ValueError, match="site_color_accent"):
        SourceConfig(**_minimal_kwargs(site_color_accent=bad))


@pytest.mark.parametrize("ok", ["#000000", "#ffd23f", "#FFFFFF", "#abcDEF"])
def test_site_color_accent_valid_accepted(ok):
    cfg = SourceConfig(**_minimal_kwargs(site_color_accent=ok))
    assert cfg.site_color_accent == ok


# ---------------------------------------------------------------------------
# Champs requis : absent vs null (issue #17)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_field",
    ["title", "reco_prefix", "hosts"],
)
def test_from_dict_field_present_but_null_treated_as_missing(missing_field):
    payload = {
        "id": "x", "title": "X", "reco_prefix": "xx", "hosts": ["A"],
    }
    payload[missing_field] = None
    with pytest.raises(ValueError, match="requis|manquants"):
        SourceConfig.from_dict(payload)


# ---------------------------------------------------------------------------
# expected_id (issue #5)
# ---------------------------------------------------------------------------


def test_from_dict_expected_id_injected_when_missing():
    """Si `expected_id` est fourni et `payload["id"]` absent, on injecte."""
    cfg = SourceConfig.from_dict(
        {"title": "X", "reco_prefix": "xx", "hosts": ["A"]},
        expected_id="x",
    )
    assert cfg.id == "x"


def test_from_dict_expected_id_mismatch_raises():
    with pytest.raises(ValueError, match="mismatch"):
        SourceConfig.from_dict(
            {"id": "y", "title": "Y", "reco_prefix": "yy", "hosts": ["A"]},
            expected_id="x",
        )


# ---------------------------------------------------------------------------
# Champ `extra` (issue #13)
# ---------------------------------------------------------------------------


def test_unknown_field_preserved_in_extra():
    """Champ inconnu → stocké dans `extra` (forward-compat soft)."""
    cfg = SourceConfig.from_dict(
        {
            "id": "x", "title": "X", "reco_prefix": "xx", "hosts": ["A"],
            "myCustomField": "value",
        },
    )
    assert cfg.extra["myCustomField"] == "value"


def test_extra_reassignment_forbidden_by_frozen():
    """`extra` ne peut pas être *réassigné* (frozen=True). La mutation
    in-place reste possible — c'est un compromis assumé pour rester
    compatible avec `dataclasses.asdict` (cf. issue #13)."""
    cfg = SourceConfig(**_minimal_kwargs(extra={"k": "v"}))
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.extra = {"x": "y"}  # type: ignore[misc]


def test_extra_is_defensive_copy():
    """Mutation de la source ne contamine pas `cfg.extra` (copy at build)."""
    source = {"k": "v"}
    cfg = SourceConfig(**_minimal_kwargs(extra=source))
    source["k"] = "modified"
    assert cfg.extra["k"] == "v"


def test_extra_default_is_empty_dict():
    cfg = SourceConfig(**_minimal_kwargs())
    assert len(cfg.extra) == 0


def test_extra_non_mapping_raises():
    with pytest.raises(TypeError, match="extra"):
        SourceConfig(**_minimal_kwargs(extra=["not", "a", "mapping"]))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# schemaVersion (issue #27)
# ---------------------------------------------------------------------------


def test_schema_version_default_is_1():
    cfg = SourceConfig(**_minimal_kwargs())
    assert cfg.schema_version == 1


def test_schema_version_future_warns(caplog):
    import logging
    payload = {
        "id": "x", "title": "X", "reco_prefix": "xx", "hosts": ["A"],
        "schemaVersion": 999,
    }
    with caplog.at_level(logging.WARNING, logger="reco.config"):
        cfg = SourceConfig.from_dict(payload)
    assert cfg.schema_version == 999
    assert any("schemaVersion" in r.message or "999" in r.message
               for r in caplog.records)


# ---------------------------------------------------------------------------
# enabled (issue #26)
# ---------------------------------------------------------------------------


def test_enabled_default_is_true():
    cfg = SourceConfig(**_minimal_kwargs())
    assert cfg.enabled is True


def test_enabled_can_be_false():
    cfg = SourceConfig(**_minimal_kwargs(enabled=False))
    assert cfg.enabled is False


# ---------------------------------------------------------------------------
# Round-trip dataclasses.asdict ↔ from_dict (issue #36)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"description": "txt", "rss_url": "https://x"},
        {"extraction_anchor_patterns": ("ta reco",)},
        {"youtube_title_suffix_patterns": ("foo", "bar")},
        {"avoid_brands": ("X", "Y"), "enabled": False},
    ],
)
def test_from_dict_asdict_round_trip(overrides):
    cfg = SourceConfig(**_minimal_kwargs(**overrides))
    # asdict convertit les tuples en listes (norme JSON) — c'est OK car
    # from_dict re-coerce vers tuple.
    data = dataclasses.asdict(cfg)
    cfg2 = SourceConfig.from_dict(data)
    assert cfg2 == cfg


def test_from_dict_unknown_field_warns(caplog):
    """Champs inconnus → warning non-bloquant (forward-compat soft)."""
    import logging
    payload = {
        "id": "x",
        "title": "X",
        "reco_prefix": "xx",
        "hosts": ["A"],
        "unknown_field": "value",
    }
    with caplog.at_level(logging.WARNING, logger="reco.config"):
        cfg = SourceConfig.from_dict(payload)
    assert cfg.id == "x"
    assert any("unknown_field" in r.message for r in caplog.records)
