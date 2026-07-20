"""Tests de l'adaptateur Astro ↔ Python (camelCase → snake_case)."""

from __future__ import annotations

from tools.config.astro_adapter import (
    ALIASES,
    ASTRO_ONLY_FIELDS,
    normalize_payload,
)


# ---------------------------------------------------------------------------
# normalize_payload
# ---------------------------------------------------------------------------


def test_normalize_renames_camel_case_aliases():
    payload = {
        "id": "x",
        "rssUrl": "https://r",
        "youtubeChannel": "https://yt",
        "spotifyShowId": "spid",
        "website": "https://site",
        "recoPrefix": "x",
        "transcriptDefaultSource": "acast",
        "extractionAnchorPatterns": ["ta reco"],
        "siteColorAccent": "#fff",
        "avoidBrands": ["X"],
    }
    out = normalize_payload(payload)
    assert out == {
        "id": "x",
        "rss_url": "https://r",
        "youtube_channel_url": "https://yt",
        "spotify_show_id": "spid",
        "site_url": "https://site",
        "reco_prefix": "x",
        "transcript_default_source": "acast",
        "extraction_anchor_patterns": ["ta reco"],
        "site_color_accent": "#fff",
        "avoid_brands": ["X"],
    }


def test_normalize_drops_astro_only_fields():
    payload = {"id": "x", "theme": {"colors": {}}, "tagline": "blah"}
    out = normalize_payload(payload)
    assert "theme" not in out
    assert "tagline" not in out
    assert out == {"id": "x"}


def test_normalize_drops_cover_image_anticipation():
    """``coverImage`` est anticipé dans la roadmap — pas de warning."""
    out = normalize_payload({"id": "x", "coverImage": "x.png"})
    assert "coverImage" not in out


def test_normalize_preserves_unknown_fields_for_warning_upstream():
    """L'adaptateur ne décide PAS de filtrer les inconnus — c'est le rôle
    du schéma de logger un warning. On laisse passer."""
    out = normalize_payload({"id": "x", "futureField": 42})
    assert out["futureField"] == 42


def test_normalize_does_not_mutate_input():
    payload = {"id": "x", "rssUrl": "r"}
    normalize_payload(payload)
    assert "rss_url" not in payload
    assert payload["rssUrl"] == "r"


def test_normalize_youtube_title_suffix_patterns_alias():
    """Nouveau champ pipeline-only (cf. migration `_SUFFIX_RE`)."""
    out = normalize_payload({"youtubeTitleSuffixPatterns": ["a"]})
    assert out == {"youtube_title_suffix_patterns": ["a"]}


def test_normalize_schema_version_alias():
    out = normalize_payload({"schemaVersion": 2})
    assert out == {"schema_version": 2}


def test_aliases_table_is_camel_to_snake_only():
    """Sanity : aucune clé alias contenant `_` (ce sont des cibles, pas
    des sources)."""
    for k in ALIASES:
        assert "_" not in k, f"{k!r} ressemble à snake_case"
    for v in ALIASES.values():
        # Cibles snake_case uniquement
        assert v == v.lower()


def test_astro_only_fields_contains_theme_and_tagline():
    assert "theme" in ASTRO_ONLY_FIELDS
    assert "tagline" in ASTRO_ONLY_FIELDS
