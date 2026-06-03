"""Tests pour tools/review_links.py — cible 100%."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from review_links import (
    AUTO_PLATFORMS_BY_TYPE, _URL_BUILDERS, auto_url, auto_urls_for,
)


# Mapping label → type qui « héberge » ce label (pour le test paramétré).
_LABEL_TO_TYPE: dict[str, str] = {}
for t, labels in AUTO_PLATFORMS_BY_TYPE.items():
    for label in labels:
        _LABEL_TO_TYPE.setdefault(label, t)


@pytest.mark.parametrize("label", sorted(_LABEL_TO_TYPE))
def test_auto_url_for_each_label_returns_https_url(label):
    """Chaque label connu doit générer une URL https valide pour un reco minimal."""
    reco = {"title": "Test", "creator": "X", "types": [_LABEL_TO_TYPE[label]]}
    url = auto_url(label, reco)
    if label == "Site officiel":
        # Sans externalIds.website → None par contrat.
        assert url is None
        return
    assert url is not None
    assert url.startswith("https://"), f"{label} → {url}"


def test_auto_url_uses_external_id_when_present():
    reco = {
        "title": "X", "types": ["film"],
        "externalIds": {
            "spotify": "https://open.spotify.com/track/42",
            "deezer": "https://deezer.com/track/9",
            "justwatch": "https://www.justwatch.com/fr/film/x",
            "website": "https://example.com",
            "youtube": "ABCDEFGHIJK",
            "instagram": "@alice",
        },
    }
    assert auto_url("Spotify", reco) == "https://open.spotify.com/track/42"
    assert auto_url("Deezer", reco) == "https://deezer.com/track/9"
    assert auto_url("JustWatch", reco) == "https://www.justwatch.com/fr/film/x"
    assert auto_url("Site officiel", reco) == "https://example.com"
    assert auto_url("YouTube", reco) == "https://www.youtube.com/watch?v=ABCDEFGHIJK"
    assert auto_url("Instagram", reco) == "https://www.instagram.com/alice/"


def test_auto_url_falls_back_to_search():
    reco = {"title": "X", "creator": "Y", "types": ["album"]}
    assert "search/" in auto_url("Spotify", reco)
    assert "search/" in auto_url("Deezer", reco)
    assert "recherche" in auto_url("JustWatch", reco)
    # Instagram tombe sur duckduckgo/google search
    assert "site%3Ainstagram.com" in auto_url("Instagram", reco)


def test_auto_url_for_unknown_label_returns_none():
    assert auto_url("UnknownLabel", {"title": "X"}) is None


def test_auto_url_for_isbn_uses_direct_search():
    reco = {
        "title": "X", "types": ["livre"],
        "externalIds": {"isbn": "9782070000000"},
    }
    url = auto_url("Place des Libraires", reco)
    assert "9782070000000" in url


def test_auto_url_places_libraires_no_isbn_uses_title():
    reco = {"title": "Mon livre", "types": ["livre"]}
    url = auto_url("Place des Libraires", reco)
    assert "Mon%20livre" in url


def test_auto_url_youtube_canonical_id_vs_url_vs_search():
    # ID 11 chars
    r1 = {"title": "X", "types": ["video"], "externalIds": {"youtube": "abcdEFGHIJ_"}}
    assert auto_url("YouTube", r1) == "https://www.youtube.com/watch?v=abcdEFGHIJ_"
    # URL canonique (youtu.be)
    r2 = {"title": "X", "types": ["video"], "externalIds": {"youtube": "https://youtu.be/xyz"}}
    assert auto_url("YouTube", r2) == "https://youtu.be/xyz"
    # URL canonique (www.youtube.com)
    r3 = {"title": "X", "types": ["video"], "externalIds": {"youtube": "https://www.youtube.com/watch?v=k"}}
    assert auto_url("YouTube", r3) == "https://www.youtube.com/watch?v=k"
    # Pas d'ID, pas d'URL → search
    r4 = {"title": "X", "types": ["video"]}
    assert auto_url("YouTube", r4).startswith("https://www.youtube.com/results?")


def test_auto_url_youtube_rejects_suspicious_host():
    """Un host trompeur (`youtube.com.evil.com`) doit retomber sur la search."""
    reco = {
        "title": "X", "types": ["video"],
        "externalIds": {"youtube": "https://www.youtube.com.evil.com/watch?v=KO"},
    }
    url = auto_url("YouTube", reco)
    assert "youtube.com.evil.com" not in url
    assert url.startswith("https://www.youtube.com/results?")


def test_auto_url_youtube_rejects_javascript_scheme():
    reco = {
        "title": "X", "types": ["video"],
        "externalIds": {"youtube": "javascript:alert(1)"},
    }
    assert auto_url("YouTube", reco).startswith("https://www.youtube.com/results")


def test_auto_url_spotify_for_podcast_includes_shows_suffix():
    """Drift fix : Spotify pour podcast doit ajouter /shows."""
    reco = {"title": "Un Bon Moment", "types": ["podcast"]}
    url = auto_url("Spotify", reco)
    assert url.endswith("/shows")


def test_auto_url_deezer_for_podcast_includes_podcast_suffix():
    """Drift fix : Deezer pour podcast doit ajouter /podcast."""
    reco = {"title": "Un Bon Moment", "types": ["podcast"]}
    url = auto_url("Deezer", reco)
    assert url.endswith("/podcast")


def test_auto_url_spotify_for_album_no_suffix():
    reco = {"title": "Pop", "types": ["album"]}
    url = auto_url("Spotify", reco)
    assert not url.endswith("/shows")


def test_auto_url_instagram_strips_at_handle():
    reco = {"title": "X", "types": ["artiste"], "externalIds": {"instagram": "@bob"}}
    assert auto_url("Instagram", reco) == "https://www.instagram.com/bob/"


def test_auto_url_instagram_empty_handle_falls_back_to_search():
    reco = {"title": "X", "types": ["artiste"], "externalIds": {"instagram": ""}}
    assert "site%3Ainstagram.com" in auto_url("Instagram", reco)


def test_auto_url_site_officiel_returns_none_without_website():
    reco = {"title": "X", "types": ["artiste"]}
    assert auto_url("Site officiel", reco) is None


def test_auto_url_explicit_in_type_overrides_reco_types():
    """`in_type=...` doit primer sur l'inférence par `reco.types`."""
    reco = {"title": "X", "types": ["musique"]}
    # En musique : pas de suffixe. Mais on force podcast → suffixe doit
    # apparaître.
    url = auto_url("Spotify", reco, in_type="podcast")
    assert url.endswith("/shows")


def test_auto_urls_for_returns_dict_for_multi_type():
    reco = {"title": "Mix", "types": ["film", "album"]}
    out = auto_urls_for(reco)
    assert "JustWatch" in out
    assert "Spotify" in out
    assert "Bandcamp" in out


def test_auto_urls_for_skips_none_labels():
    """`Site officiel` sans website → omis du dict."""
    reco = {"title": "X", "types": ["artiste"]}
    out = auto_urls_for(reco)
    assert "Site officiel" not in out
    assert "Instagram" in out


def test_auto_urls_for_includes_podcast_specific_suffix():
    reco = {"title": "Podcast X", "types": ["podcast"]}
    out = auto_urls_for(reco)
    assert out["Spotify"].endswith("/shows")
    assert out["Deezer"].endswith("/podcast")


def test_auto_urls_for_dedups_shared_labels_across_types():
    """Pour une reco musique+album, le label Spotify n'apparaît qu'une fois."""
    reco = {"title": "X", "types": ["musique", "album"]}
    out = auto_urls_for(reco)
    # On vérifie juste qu'on a une valeur pour Spotify et que le code de dédup
    # est passé (label déjà présent → continue, cf. ligne 180).
    assert out.get("Spotify", "").startswith("https://open.spotify.com")


def test_auto_urls_for_empty_types_returns_empty_dict():
    assert auto_urls_for({"title": "X", "types": []}) == {}
    assert auto_urls_for({"title": "X"}) == {}


# Parité TS/Py : compare les labels de merchants.ts à ceux d'auto_url.
_MERCHANTS_TS = Path(__file__).parent.parent / "src" / "data" / "merchants.ts"


def test_auto_url_labels_cover_all_platforms_in_merchants_ts():
    """Si un nouveau `label: '...'` apparaît dans merchants.ts, on doit le
    connaître côté Python sinon le formulaire d'override le perdra silencieusement."""
    if not _MERCHANTS_TS.exists():
        pytest.skip("merchants.ts non présent dans cet environnement")
    text = _MERCHANTS_TS.read_text(encoding="utf-8")
    # Récupère tous les `label: '...'` ou `label: "..."` à l'exception de la
    # définition de l'interface (`label: string`).
    labels = set(re.findall(r"label:\s*['\"]([^'\"]+)['\"]", text))
    # Vire les labels qui n'apparaissent pas dans resolveLinks (ex. customLinks,
    # `customLinks` est un user-defined). On vérifie inclusion stricte.
    known = set(_URL_BUILDERS)
    missing = labels - known
    assert not missing, f"Labels présents dans merchants.ts mais absents de _URL_BUILDERS : {missing}"
