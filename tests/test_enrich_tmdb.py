"""Tests du résolveur de liens TMDB (tools/enrich_tmdb.py).

On teste uniquement la fonction pure `_provider_link` (mapping nom-provider →
URL + ethics). Pas d'appel réseau à TMDB ici.
"""
from __future__ import annotations

import pytest

from enrich_tmdb import _provider_link


# ===== Mapping exact ======================================================
@pytest.mark.parametrize("name,host,expected_ethics", [
    ("Netflix",          "netflix.com",       "neutral"),
    ("Apple TV",         "tv.apple.com",      "neutral"),
    ("Disney Plus",      "disneyplus.com",    "neutral"),
    ("Mubi",             "mubi.com",          "indie"),
    ("Arte",             "arte.tv",           "indie"),
    ("Amazon Prime Video", "primevideo.com",  "avoid"),
    ("Canal+",           "canalplus.com",     "avoid"),
])
def test_exact_provider_mapped_to_proper_host(name, host, expected_ethics):
    link = _provider_link(name, "Mortel")
    assert host in link["url"]
    assert link["ethics"] == expected_ethics
    assert link["label"] == name


# ===== Patterns substring =================================================
def test_apple_tv_store_pattern_routed_to_apple_tv():
    """« Apple TV Store » doit aller sur tv.apple.com (via pattern 'apple tv')."""
    link = _provider_link("Apple TV Store", "Mortel")
    assert "tv.apple.com" in link["url"]
    assert link["ethics"] == "neutral"


def test_netflix_with_ads_pattern_routed_to_netflix():
    link = _provider_link("Netflix Standard with Ads", "Mortel")
    assert "netflix.com" in link["url"]


def test_amazon_anything_marked_avoid():
    """Tout provider contenant « amazon » → ethics='avoid'."""
    for name in ("Amazon Prime Video with Ads", "MUBI Amazon Channel",
                 "HBO Max Amazon Channel"):
        link = _provider_link(name, "Mortel")
        assert link["ethics"] == "avoid", f"{name} devrait être avoid"
        assert "primevideo.com" in link["url"]


def test_canal_anything_marked_avoid():
    for name in ("Canal VOD", "Canal+ Series", "myCANAL"):
        link = _provider_link(name, "Mortel")
        assert link["ethics"] == "avoid"
        assert "canalplus.com" in link["url"]


# ===== Fallback ===========================================================
def test_unknown_provider_falls_back_to_duckduckgo():
    link = _provider_link("Plateforme Inconnue 42", "Mortel")
    assert "duckduckgo.com" in link["url"]
    assert link["ethics"] == "neutral"
    # Le label doit rester celui d'origine pour l'affichage.
    assert link["label"] == "Plateforme Inconnue 42"


# ===== URL encoding =======================================================
def test_url_contains_encoded_title():
    """Le titre est URL-encoded (espaces → %20)."""
    link = _provider_link("Netflix", "Full Metal Jacket")
    assert "Full%20Metal%20Jacket" in link["url"]
