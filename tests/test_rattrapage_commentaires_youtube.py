"""Tests de `tools/rattrapage_commentaires_youtube.py`.

Rien ne part sur le réseau : la fausse session de `test_commentaire_youtube`
joue le site et l'API YouTube.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import rattrapage_commentaires_youtube as rc
from test_commentaire_youtube import ENV, Reponse, Session


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch):
    """Trois anciens épisodes et un récent, chacun avec une reco validée."""
    episodes = tmp_path / "episodes" / "ubm"
    recos = tmp_path / "recos" / "ubm"
    episodes.mkdir(parents=True)
    recos.mkdir(parents=True)
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    for guid, date, video in (("a", "2021-02-14", "AAA"), ("b", "2023-05-01", "BBB"),
                              ("c", "2022-01-01", "CCC"), ("yt-new", "2026-10-23", "new")):
        (episodes / f"{guid}.json").write_text(json.dumps({
            "guid": guid, "date": date, "title": f"avec {guid.upper()}",
            "youtubeUrl": f"https://www.youtube.com/watch?v={video}"}), encoding="utf-8")
        (recos / f"{guid}.json").write_text(json.dumps({
            "id": f"r-{guid}", "episodeGuid": guid, "status": "validated",
            "title": f"Oeuvre {guid}", "types": ["film"], "timestamp": "00:01:10",
            "transcriptSource": "youtube"}), encoding="utf-8")
    return tmp_path


def _page():
    return "".join(f"Oeuvre {g}" for g in ("a", "b", "c"))


def _lancer(corpus, session, nombre=1, notes=None, recap=False, le="2026-11-02T14:00:00"):
    notes = [] if notes is None else notes
    chemin = corpus / "etat.json"
    n = rc.rattraper("ubm", nombre, notes.append, chemin=chemin, session=session,
                     env=ENV, maintenant=lambda: le, recap=recap)
    return n, json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else None, notes


def test_video_id():
    assert rc.video_id("https://www.youtube.com/watch?v=8jkQGlHZcs0") == "8jkQGlHZcs0"
    assert rc.video_id("https://youtu.be/8jkQGlHZcs0") == "8jkQGlHZcs0"
    assert rc.video_id(None) is None


def test_la_plus_recente_d_abord_et_jamais_les_episodes_de_la_chaine(corpus):
    file = rc.en_attente("ubm", {"postes": {}, "de_cote": {}}, ENV)
    assert [video for _, video, _ in file] == ["BBB", "CCC", "AAA"]


def test_poste_un_seul_commentaire_par_appel_et_s_en_souvient(corpus):
    session = Session(page=_page())
    n, etat, notes = _lancer(corpus, session)
    assert n == 1
    assert session.postes[0]["json"]["snippet"]["videoId"] == "BBB"
    assert "1:10 🎬 Oeuvre b" in session.postes[0]["json"]["snippet"]["topLevelComment"][
        "snippet"]["textOriginal"]
    assert etat["postes"]["b"]["commentaire"] == "UgzCommentaire"
    assert notes == []  # un succès ne sonne pas dans Matrix
    # Le passage suivant prend la vidéo d'après.
    _lancer(corpus, session)
    assert session.postes[1]["json"]["snippet"]["videoId"] == "CCC"


def test_inactif_sans_secrets(corpus):
    session = Session(page=_page())
    n = rc.rattraper("ubm", 4, lambda _: None, chemin=corpus / "e.json",
                     session=session, env={})
    assert n == 0 and session.postes == []


def test_page_sans_ses_recos_met_la_video_de_cote(corpus):
    session = Session(page="rien")
    n, etat, notes = _lancer(corpus, session)
    assert n == 0 and session.postes == []
    assert "ne montre pas" in etat["de_cote"]["b"]["raison"]
    assert len(notes) == 1
    # Mise de côté : le passage suivant passe à la vidéo d'après.
    assert [v for _, v, _ in rc.en_attente("ubm", etat, ENV)] == ["CCC", "AAA"]


def test_commentaires_fermes_met_la_video_de_cote(corpus):
    class Fermee(Session):
        def post(self, url, timeout, data=None, json=None, headers=None):
            if url == rc.cy.JETON_URL:
                return super().post(url, timeout, data=data)
            return Reponse(403)
    n, etat, notes = _lancer(corpus, Fermee(page=_page()))
    assert n == 0 and "HTTP 403" in etat["de_cote"]["b"]["raison"]


def test_jeton_refuse_ne_met_rien_de_cote(corpus):
    n, etat, notes = _lancer(corpus, Session(page=_page(), statut_jeton=401))
    assert n == 0 and etat is None
    assert "jeton refusé" in notes[0]


def test_fin_du_rattrapage_annoncee_une_fois(corpus):
    session = Session(page=_page())
    n, etat, notes = _lancer(corpus, session, nombre=4)
    assert n == 3 and notes == []
    _, etat, notes = _lancer(corpus, session)
    assert etat["termine"] and "terminé : 3 vidéo(s)" in notes[0]
    _, _, notes = _lancer(corpus, session)
    assert notes == []


def test_recapitulatif_du_jour_au_dernier_passage(corpus):
    session = Session(page=_page())
    _lancer(corpus, session, le="2026-11-01T20:00:00")  # la veille : hors du récapitulatif
    _lancer(corpus, session)
    _, _, notes = _lancer(corpus, session, recap=True)
    assert notes == [("💬 Rattrapage YouTube du jour : 2 vidéo(s) commentée(s) "
                      "(avec C ; avec A). Reste 0 vidéo(s).")]


def test_pas_de_recapitulatif_sans_commentaire_du_jour(corpus):
    session = Session(page=_page())
    _lancer(corpus, session, le="2026-11-01T20:00:00")
    _, _, notes = _lancer(corpus, Session(page="rien"), recap=True, le="2026-11-02T20:00:00")
    # Seule la mise de côté sonne ; aucun récapitulatif vide.
    assert len(notes) == 1 and "mis de côté" in notes[0]
