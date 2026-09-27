"""Tests des créateurs qui portent PLUSIEURS noms — couche pure.

Un `creator` comme « Grand Corps Malade & Styleto » ou « Ben Mazué feat. Yoa »
doit être reconnu face à une API qui n'en crédite qu'un ; et la réponse de l'API
porte parfois elle aussi le duo entier. Les deux côtés sont donc décomposés.

Le fil rouge de ces tests est l'ASYMÉTRIE assumée entre les deux branches de
`verdict` : pour un album ou un morceau, le titre sert d'ancre et autorise le
découpage sur « & » ; une page ARTISTE n'a pas d'ancre et le refuse, sans quoi
« Simon & Garfunkel » et « Simon » deviendraient interchangeables.

Séparé de `test_matching.py`, qui passait 500 lignes (règle du projet).
"""
from __future__ import annotations

import pytest

import enrich_music_links as m


def _cand(artist, title="", ident="1", platform=m.PLATFORM_DEEZER, kind="album"):
    """Même fabrique que `test_matching`, gardée locale : un fichier de tests ne
    doit pas dépendre d'un autre."""
    return m.Candidate(platform, kind, f"https://deezer.com/{ident}", artist,
                       title, ident=ident)


# ===== créateurs multiples : ce que le titre autorise, et ce qu'il interdit ===
DUO_RECO = {"title": "Le prochain rêve", "creator": "Grand Corps Malade & Styleto"}
FEAT_RECO = {"title": "Rupture", "creator": "Ben Mazué feat. Yoa"}


def test_verdict_accepts_a_featuring_credit():
    """Les APIs créditent « Rupture » à Ben Mazué seul."""
    chosen, reason, _ = m.verdict(
        FEAT_RECO, [_cand("Ben Mazué", "Rupture", kind="track")],
        want_artist_page=False)
    assert reason == m.REASON_LINKED
    assert chosen.artist == "Ben Mazué"


def test_verdict_accepts_an_ampersand_half_when_the_title_anchors_it():
    chosen, reason, _ = m.verdict(
        DUO_RECO, [_cand("Grand Corps Malade", "Le prochain rêve", kind="track")],
        want_artist_page=False)
    assert reason == m.REASON_LINKED
    assert chosen is not None


def test_verdict_refuses_an_ampersand_half_when_the_title_does_not_match():
    """Un nom seul ne suffit jamais : sans le titre, aucun lien."""
    chosen, reason, _ = m.verdict(
        DUO_RECO, [_cand("Grand Corps Malade", "Un autre titre", kind="track")],
        want_artist_page=False)
    assert (chosen, reason) == (None, m.REASON_NO_MATCH)


def test_verdict_artist_page_refuses_half_of_an_ampersand_name():
    """Le garde-fou de non-régression : « Simon & Garfunkel » n'est pas « Simon ».

    Une page ARTISTE n'a aucun titre d'œuvre pour ancrer la comparaison. Y
    accepter la moitié d'un nom enverrait la reco vers un artiste sans rapport.
    """
    chosen, reason, _ = m.verdict(
        {"title": "Simon & Garfunkel", "creator": "Simon & Garfunkel"},
        [_cand("Simon", kind="artist")], want_artist_page=True)
    assert (chosen, reason) == (None, m.REASON_NO_MATCH)


def test_verdict_still_refuses_a_homonym_that_shares_only_the_title():
    """Le découpage ne doit pas rouvrir la porte fermée par le garde-fou d'origine."""
    chosen, reason, _ = m.verdict(
        DUO_RECO, [_cand("Un Inconnu", "Le prochain rêve", kind="track")],
        want_artist_page=False)
    assert (chosen, reason) == (None, m.REASON_ARTIST_MISMATCH)


# ===== symétrie : l'API crédite parfois le duo entier =======================
def test_artist_matches_creator_splits_the_api_side_on_featuring():
    """Le découpage vaut des DEUX côtés : l'API aussi peut porter la mention.

    Sans cette symétrie, un « Ben Mazué feat. Yoa » renvoyé par une API face à un
    corpus qui n'écrit que « Ben Mazué » tombait en `artist-mismatch`.
    """
    assert m.artist_matches_creator("Ben Mazué feat. Yoa", "Ben Mazué")


def test_artist_matches_collaborator_splits_the_api_side_on_the_ampersand():
    """Mesuré le 2026-09-25 : Apple crédite « Rupture » à « Ben Mazué & Yoa »,
    et la comparaison des chaînes entières donnait 0,82 pour 0,88 requis."""
    assert m.artist_matches_collaborator("Ben Mazué & Yoa", "Ben Mazué")


@pytest.mark.parametrize("distant,createur", [
    ("Ben Mazué", "Ben Mazué"),
    ("Ben Mazué feat. Yoa", "Ben Mazué"),
    ("Damon Albarn, Jamie Hewlett", "Damon Albarn"),
])
def test_artist_matches_collaborator_false_without_any_ampersand(distant, createur):
    """Le garde : sans « & » découpé d'un côté ou de l'autre, rien n'est accordé.

    La fonction retomberait sinon sur `artist_matches_creator`, et ses appelants
    relâcheraient le garde-fou du titre sans le savoir.
    """
    assert not m.artist_matches_collaborator(distant, createur)


def test_verdict_accepts_an_api_duo_when_the_title_anchors_it():
    chosen, reason, _ = m.verdict(
        {"title": "Rupture", "creator": "Ben Mazué"},
        [_cand("Ben Mazué & Yoa", "Rupture", kind="track")],
        want_artist_page=False)
    assert reason == m.REASON_LINKED
    assert chosen is not None


def test_verdict_refuses_an_api_duo_when_the_title_differs():
    chosen, reason, _ = m.verdict(
        {"title": "Rupture", "creator": "Ben Mazué"},
        [_cand("Ben Mazué & Yoa", "Un autre titre", kind="track")],
        want_artist_page=False)
    assert (chosen, reason) == (None, m.REASON_NO_MATCH)


def test_verdict_artist_page_refuses_an_api_duo_for_half_a_name():
    """Non-régression, côté API cette fois : une reco de « Simon » ne doit pas
    atterrir sur la page du duo « Simon & Garfunkel », faute d'ancre de titre."""
    chosen, reason, _ = m.verdict(
        {"title": "Simon", "creator": "Simon"},
        [_cand("Simon & Garfunkel", kind="artist")], want_artist_page=True)
    assert (chosen, reason) == (None, m.REASON_NO_MATCH)
