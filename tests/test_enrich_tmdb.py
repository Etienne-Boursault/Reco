"""Tests de la table des plateformes TMDB (tools/tmdb_providers.py).

On teste les fonctions pures `_provider_link` (mapping nom-provider → URL +
ethics) et `liens_des_plateformes` (une liste de noms → des boutons sans
doublon). Pas d'appel réseau à TMDB ici.
"""
from __future__ import annotations

import pytest

from tmdb_providers import _provider_link, liens_des_plateformes


# ===== Mapping exact ======================================================
@pytest.mark.parametrize("name,host,expected_ethics", [
    ("Netflix",          "netflix.com",       "neutral"),
    ("Apple TV",         "tv.apple.com",      "neutral"),
    ("Sooner",           "sooner.fr/catalogue", "neutral"),
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


# ===== Plateformes sans recherche publique ================================
@pytest.mark.parametrize("name", [
    "Premiere Max", "VIVA by videofutur", "Molotov TV", "TF1+", "Disney Plus",
    "Orange VOD", "SFR Play",
])
def test_plateforme_sans_recherche_ne_recoit_aucun_lien(name):
    """Leur recherche menait à une page introuvable (constaté le 2026-11-02),
    ou leur domaine a disparu (Orange VOD et SFR Play, 2026-11-13) : pas de
    lien plutôt qu'un lien mort, et surtout pas le repli DuckDuckGo."""
    assert _provider_link(name, "Mortel") is None


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


# ===== Une liste de plateformes → des boutons ================================
def test_deux_offres_qui_menent_a_la_meme_recherche_donnent_un_seul_bouton():
    """« Paramount Plus » et « Paramount Plus Premium » : même recherche, un
    seul bouton (doublon vu sur S6-E09, 2026-11-13)."""
    liens = liens_des_plateformes(["Paramount Plus", "Paramount Plus Premium"], "Mortel")
    assert [lien["label"] for lien in liens] == ["Paramount Plus"]


def test_le_nom_general_de_la_plateforme_l_emporte_sur_une_offre_particuliere():
    """« HBO Max Amazon Channel » lu avant « Amazon Video » : la recherche est
    celle de Prime Video, le bouton porte le nom général, à la place du premier."""
    liens = liens_des_plateformes(["Netflix", "HBO Max Amazon Channel", "Amazon Video"], "Mortel")
    assert [lien["label"] for lien in liens] == ["Netflix", "Amazon Video"]


def test_un_nom_repete_ou_sans_recherche_ne_donne_rien_de_plus():
    liens = liens_des_plateformes(["Netflix", "Orange VOD", "Netflix", "SFR Play"], "Mortel")
    assert [lien["label"] for lien in liens] == ["Netflix"]


def test_le_bouton_fusionne_prend_aussi_le_marqueur_ethique_de_la_regle_exacte(monkeypatch):
    """Le nom et le marqueur viennent de la même règle : jamais un nom de
    plateforme « neutre » sous le marqueur d'une offre « indie », ni l'inverse."""
    import tmdb_providers
    regles = dict(tmdb_providers.PROVIDER_RULES)
    regles["Kino"] = {"url": "https://mubi.com/fr/films?q={q}", "ethics": "neutral"}
    monkeypatch.setattr(tmdb_providers, "PROVIDER_RULES", regles)
    liens = liens_des_plateformes(["MUBI Truc", "Kino"], "Mortel")
    assert [(lien["label"], lien["ethics"]) for lien in liens] == [("Kino", "neutral")]
