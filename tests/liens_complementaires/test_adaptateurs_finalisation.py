"""Raccordement des trois passes à la chaîne de venus.

Deux choses : chaque adaptateur limite l'outil à l'épisode et écrit ; et
`finaliser` déroule les passes dans l'ORDRE imposé — les plateformes lisent ce
que TMDB vient de poser, YouTube Music ce que Wikidata vient de poser.
"""
from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest

import common
import finalisation_passes as fp
import traiter_nouveaux_episodes as tne


@pytest.mark.parametrize("adaptateur,cible", [
    (fp.liens_plateformes, "streaming_links.run"),
    (fp.liens_jeux, "jeux_wikidata.run"),
    (fp.liens_youtube_music, "youtube_music_links.run"),
])
def test_chaque_adaptateur_vise_lepisode_et_ecrit(monkeypatch, adaptateur, cible):
    appels = []
    monkeypatch.setattr(cible, lambda **kw: appels.append(kw) or "rapport")

    assert adaptateur("un-bon-moment", {"r-1"}) == "rapport"

    (recu,) = appels
    assert recu["root"] == common.RECOS_DIR and recu["source"] == "un-bon-moment"
    assert recu["ids"] == {"r-1"} and recu["apply"] is True


def _rapport(servies=()):
    return SimpleNamespace(servies=set(servies))


def test_finaliser_deroule_les_passes_dans_lordre_et_les_compte(monkeypatch):
    ordre = []

    def passe(nom, servies=()):
        return lambda _source, ids: ordre.append((nom, ids)) or _rapport(servies)

    episode = {"guid": "yt-1", "title": "S6-E04"}
    monkeypatch.setattr(tne, "a_finaliser", lambda *_a: [(None, episode)])
    monkeypatch.setattr(tne, "_recos_de", lambda *_a: [{"id": "r-1", "links": [{"url": "x"}]}])
    messages = []
    state = {"finalized": [], "lastErrors": {}}

    tne.finaliser("src", messages.append, state,
                  liens=lambda *_a: SimpleNamespace(linked=[], outcomes=[]),
                  fiches=passe("tmdb"), video=passe("fiches"), wikidata=passe("wikidata"),
                  boutique=passe("boutique"), plateformes=passe("plateformes", {"r-1"}),
                  jeux=passe("jeux"), youtube_music=passe("ytmusic"),
                  publier=lambda *_a, **_k: SimpleNamespace(
                      refused=False, items_created=[], items_reused=[], mentions_created=[]),
                  lock=contextlib.nullcontext)

    assert [nom for nom, _ids in ordre] == ["tmdb", "fiches", "wikidata", "boutique",
                                           "plateformes", "jeux", "ytmusic"]
    assert all(ids == {"r-1"} for _nom, ids in ordre)
    assert state["finalized"] == ["yt-1"]
    (message,) = messages
    assert "1 lien(s) de plateforme" in message and "0 lien(s) YouTube Music" in message


def test_une_panne_dune_nouvelle_passe_ne_bloque_pas_lepisode(monkeypatch):
    def panne(*_a):
        raise RuntimeError("yt-dlp cassé")

    episode = {"guid": "yt-1"}
    monkeypatch.setattr(tne, "a_finaliser", lambda *_a: [(None, episode)])
    monkeypatch.setattr(tne, "_recos_de", lambda *_a: [])
    for nom in ("_fiches_tmdb", "_fiches_video", "_liens_wikidata", "_liens_boutique",
                "_liens_plateformes", "_liens_jeux"):
        monkeypatch.setattr(tne, nom, lambda *_a: _rapport())
    monkeypatch.setattr(tne, "_liens_youtube_music", panne)
    messages = []
    state = {"finalized": [], "lastErrors": {}}

    tne.finaliser("src", messages.append, state,
                  liens=lambda *_a: SimpleNamespace(linked=[], outcomes=[]),
                  publier=lambda *_a, **_k: SimpleNamespace(
                      refused=False, items_created=[], items_reused=[], mentions_created=[]),
                  lock=contextlib.nullcontext)

    assert state["finalized"] == ["yt-1"]
    assert "YouTube Music indisponible" in messages[0]
