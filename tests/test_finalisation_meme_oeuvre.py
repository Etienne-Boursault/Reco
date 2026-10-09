"""Passe « même œuvre » de la finalisation (`finalisation_passes.meme_oeuvre`).

Cas réel qui l'a motivée : sur S6-E04, Fleabag était recommandée pour la
quatrième fois ; les recos précédentes portaient Apple TV, Prime Video et
AlloCiné, et la chaîne a tout recherché de zéro sans les retrouver.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import finalisation_passes as fp
import traiter_nouveaux_episodes as tne

SOURCE = "demo"

PRIME = {"ethics": "avoid", "kind": "streaming", "label": "Prime Video",
         "url": "https://www.primevideo.com/-/fr/detail/0OB9NDUVQKFRSYRSCHT2A784TI"}
IMDB = {"ethics": "neutral", "kind": "info", "label": "IMDb",
        "url": "https://www.imdb.com/title/tt5687612/"}
TMDB = {"ethics": "neutral", "kind": "info", "label": "TMDB",
        "url": "https://www.themoviedb.org/tv/67070"}


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Dossier de recos temporaire, vu par `common` ET par `dataset_fixes`."""
    import common
    import dataset_fixes

    root = tmp_path / "recos"
    (root / SOURCE).mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", root)
    monkeypatch.setattr(dataset_fixes, "RECOS_DIR", root)
    return root / SOURCE


def _reco(dossier, rid, guid, links, **champs):
    doc = {"id": rid, "episodeGuid": guid, "sourceId": SOURCE, "title": "Fleabag",
           "creator": "Phoebe Waller-Bridge", "types": ["serie"], "status": "validated",
           "links": links, **champs}
    (dossier / f"{rid}.json").write_text(json.dumps(doc, ensure_ascii=False),
                                         encoding="utf-8")
    return dossier / f"{rid}.json"


def _links(path):
    return [link["url"] for link in json.loads(path.read_text(encoding="utf-8"))["links"]]


def test_episode_reco_receives_the_links_already_reviewed(corpus):
    ancienne = _reco(corpus, "0001", "ep-1", [PRIME, IMDB, TMDB])
    nouvelle = _reco(corpus, "0002", "ep-2", [IMDB, TMDB])

    rapport = fp.meme_oeuvre(SOURCE, {"0002"})

    assert rapport.servies == frozenset({"0002"})
    # Union, dans l'ordre de la première reco : la plateforme garde sa place.
    assert _links(nouvelle) == [PRIME["url"], IMDB["url"], TMDB["url"]]
    assert _links(ancienne) == [PRIME["url"], IMDB["url"], TMDB["url"]]


def test_other_episodes_are_never_rewritten(corpus):
    """La reco de l'épisode apporte un lien : l'ancienne, déjà publiée, ne bouge pas.

    Les noms de fichiers suivent l'ordre du corpus (numéros croissants) : la
    reco la plus ancienne vient en premier dans l'union.
    """
    ancienne = _reco(corpus, "0001", "ep-1", [IMDB])
    nouvelle = _reco(corpus, "0002", "ep-2", [PRIME, IMDB])
    avant = ancienne.read_text(encoding="utf-8")

    rapport = fp.meme_oeuvre(SOURCE, {"0002"})

    assert rapport.servies == frozenset()  # rien à recevoir pour « new »
    assert ancienne.read_text(encoding="utf-8") == avant
    assert _links(nouvelle) == [PRIME["url"], IMDB["url"]]


def test_homonyms_are_left_alone(corpus):
    """Garde-fou d'`align_same_work_links` : identifiants contradictoires."""
    _reco(corpus, "0001", "ep-1", [PRIME, {**TMDB, "url": "https://www.themoviedb.org/tv/1"}])
    nouvelle = _reco(corpus, "0002", "ep-2", [TMDB])

    assert fp.meme_oeuvre(SOURCE, {"0002"}).servies == frozenset()
    assert _links(nouvelle) == [TMDB["url"]]


def test_finaliser_runs_it_first_and_counts_it(tmp_path, monkeypatch):
    """Branchée en tête, sans bloquer : comptée dans le message de fin."""
    import common

    for name, sub in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("RECOS_DIR", "recos"), ("OUTPUT_DIR", "output"),
                      ("TRANSCRIPTS_DIR", "output/transcripts")):
        monkeypatch.setattr(common, name, tmp_path / sub)
    (tmp_path / "episodes" / SOURCE).mkdir(parents=True)
    (tmp_path / "recos" / SOURCE).mkdir(parents=True)
    (tmp_path / "episodes" / SOURCE / "yt-1.json").write_text(json.dumps(
        {"sourceId": SOURCE, "guid": "yt-1", "title": "Titre", "transcriptStatus": "auto"}),
        encoding="utf-8")
    _reco(tmp_path / "recos" / SOURCE, "r-1", "yt-1", [])
    ordre = []
    vide = SimpleNamespace(servies=set(), vues=0, ecrites=0, seen=0, written=0,
                           filled=[], introuvables=[])
    for nom in ("_fiches_tmdb", "_fiches_video", "_liens_wikidata", "_liens_boutique"):
        monkeypatch.setattr(tne, nom, lambda *_a, n=nom, **_k: ordre.append(n) or vide)

    def oeuvre(_source, ids):
        ordre.append("oeuvre")
        return fp.Alignement(frozenset(ids))

    def liens(*_a):
        ordre.append("liens")
        return SimpleNamespace(linked=[], outcomes=[], servies=set())

    plan = SimpleNamespace(refused=False, errors=[], drafts=[], items_created=["i"],
                           items_reused=[], mentions_created=["m"])
    inbox: list[str] = []
    tne.finaliser(SOURCE, inbox.append, tne.load_state(SOURCE), liens=liens,
                  oeuvre=oeuvre, publier=lambda *_a, **_k: plan,
                  lock=lambda: __import__("contextlib").nullcontext())

    assert ordre[:2] == ["oeuvre", "liens"]
    assert "1 lien(s) repris du corpus" in inbox[0]
