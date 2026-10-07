"""Tests de `tools/caler_citations.py` — minutage et noms calés sur la transcription.

Les exemples viennent du corpus (mesure du 2026-10-07) : « Camelot » pour
Kaamelott, Mortel annoncé à 00:13:21 et dit à 00:58:15, Before Sunrise à
00:00:00. Rien n'est écrit sans `apply=True`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import caler_citations as cc

SOURCE = "demo-source"
GUID = "yt-abc"


# ===== noms ==================================================================
@pytest.mark.parametrize(("citation", "noms", "attendue"), [
    ("Camelot, déjà ils sont arrivés avec un multicam.", ["Kaamelott"],
     "Kaamelott, déjà ils sont arrivés avec un multicam."),
    ("l'intro de Les Clés de Bagnoles, c'est la meilleure", ["Les Clés de bagnole"],
     "l'intro de Les Clés de bagnole, c'est la meilleure"),
    ("la série de Jason Seagal", ["Dispatches from Elsewhere", "Jason Segel"],
     "la série de Jason Segel"),
    ("les albums d'Aurel-san qu'on connaît", ["Orelsan"], "les albums d'Orelsan qu'on connaît"),
    ("un album de Blond Red Dead que j'adore", ["Blonde Redhead"],
     "un album de Blonde Redhead que j'adore"),
    ("c'est dans la cousine bête de Balzac", ["La Cousine Bette", "Honoré de Balzac"],
     "c'est dans La Cousine Bette de Balzac"),
    ("t'as vu le Reharsal ?", ["The Rehearsal"], "t'as vu le Rehearsal ?"),
])
def test_un_nom_mal_transcrit_prend_la_graphie_de_la_fiche(citation, noms, attendue):
    assert cc.corriger_noms(citation, noms)[0] == attendue


@pytest.mark.parametrize(("citation", "noms"), [
    # Le nom est juste, rien ne l'écorche.
    ("je vois régulièrement 8 et demi de Fellini", ["Huit et demi", "Federico Fellini"]),
    # Un mot voisin ne se recolle pas à un nom déjà juste.
    ("Yannis qui est au Roi Lion ! Je te recommande", ["Le Roi Lion"]),
    # Titre descriptif, pas un nom.
    ("Romain, je recommande son spectacle précédent", ["Romain Frayssinet (spectacle précédent)"]),
    # Titre et créateur écrivent la même personne autrement : la citation suit déjà l'un d'eux.
    ("C'est Sophia Belabbès", ["Sophia Belabbès", "Sophia Bellabès"]),
])
def test_ce_qui_n_est_pas_une_faute_reste_tel_quel(citation, noms):
    assert cc.corriger_noms(citation, noms) == (citation, [])


def test_un_mot_courant_de_l_episode_n_est_pas_un_nom_ecorche():
    citation = "Franchement, j'étais tellement ému à sept minutes."
    assert cc.corriger_noms(citation, ["L'attachement"], {"franchement"}) == (citation, [])


def test_chaque_correction_est_rendue():
    _citation, corrections = cc.corriger_noms("Moi, j'écoute Camelot tout le temps", ["Kaamelott"])
    assert corrections == [("Camelot", "Kaamelott")]


# ===== minutage ==============================================================
def _lignes(*paires: tuple[str, str]) -> list[cc.Ligne]:
    return [(cc.secondes(t), cc.mots(texte)) for t, texte in paires]


LIGNES = _lignes(
    ("00:13:00", "on parlait de tout autre chose ce jour-là"),
    ("00:13:21", "et puis il y a eu ce moment génial"),
    ("00:58:10", "bon les recos alors"),
    ("00:58:15", "moi j'ai kiffé Mortel j'ai kiffé Mortel sur Netflix"),
    ("00:58:20", "une série française en plus"),
    ("01:10:00", "franchement c'est super"),
    ("01:20:00", "franchement c'est super"),
)


def test_une_citation_dite_ailleurs_une_seule_fois_y_est_recalee():
    citation = "moi j'ai kiffé Mortel j'ai kiffé Mortel sur Netflix une série française en plus"
    assert cc.recaler(citation, "00:13:21", LIGNES) == cc.secondes("00:58:15")


def test_un_minutage_nul_ne_designe_rien():
    citation = "moi j'ai kiffé Mortel j'ai kiffé Mortel sur Netflix"
    assert cc.recaler(citation, "00:00:00", LIGNES) == cc.secondes("00:58:15")


def test_un_ecart_de_dix_secondes_ou_moins_est_laisse():
    citation = "moi j'ai kiffé Mortel j'ai kiffé Mortel sur Netflix"
    assert cc.recaler(citation, "00:58:10", LIGNES) is None


def test_une_phrase_dite_deux_fois_ailleurs_n_est_pas_deplacee():
    assert cc.recaler("franchement c'est super", "00:30:00", LIGNES) is None


def test_une_citation_introuvable_garde_son_minutage():
    assert cc.recaler("rien de tout cela n'a été dit dans l'épisode", "00:13:21", LIGNES) is None


# ===== épisode ===============================================================
@pytest.fixture
def corpus(tmp_path, monkeypatch):
    import common

    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    monkeypatch.setattr(common, "TRANSCRIPTS_DIR", tmp_path / "transcripts")
    (tmp_path / "recos" / SOURCE).mkdir(parents=True)
    transcription = common.transcript_path_for(SOURCE, GUID)
    transcription.parent.mkdir(parents=True)
    transcription.write_text(
        "[00:13:21] et puis il y a eu ce moment génial\n"
        "[00:28:54] Camelot, déjà ils sont arrivés avec un multicam et c'était intéressant.\n",
        encoding="utf-8")
    return tmp_path


def _reco(racine: Path, reco_id: str, **champs) -> Path:
    reco = {"id": reco_id, "episodeGuid": GUID, "sourceId": SOURCE, "status": "draft",
            "title": "Kaamelott", "types": ["serie"], "timestamp": "00:13:21",
            "quote": "Camelot, déjà ils sont arrivés avec un multicam et c'était intéressant.",
            **champs}
    chemin = racine / "recos" / SOURCE / f"{reco_id}.json"
    chemin.write_text(json.dumps(reco, ensure_ascii=False), encoding="utf-8")
    return chemin


def _lire(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


def test_l_episode_est_cale_et_rien_n_est_ecrit_a_blanc(corpus):
    chemin = _reco(corpus, "ubm-1")
    avant = chemin.read_text(encoding="utf-8")

    bilan = cc.caler_episode(SOURCE, GUID)

    assert bilan.noms == [("ubm-1", "Camelot", "Kaamelott")]
    assert bilan.minutages == [("ubm-1", "00:13:21", "00:28:54")]
    assert chemin.read_text(encoding="utf-8") == avant


def test_avec_apply_la_citation_et_le_minutage_sont_ecrits(corpus):
    chemin = _reco(corpus, "ubm-1")

    cc.caler_episode(SOURCE, GUID, apply=True)

    reco = _lire(chemin)
    assert reco["quote"].startswith("Kaamelott, déjà")
    assert reco["timestamp"] == "00:28:54"


def test_une_reco_ecartee_ou_d_un_autre_episode_n_est_pas_touchee(corpus):
    ecartee = _reco(corpus, "ubm-1", status="discarded")
    autre = _reco(corpus, "ubm-2", episodeGuid="yt-autre")

    bilan = cc.caler_episode(SOURCE, GUID, apply=True)

    assert bilan.noms == [] and bilan.minutages == []
    assert _lire(ecartee)["quote"].startswith("Camelot") and _lire(autre)["timestamp"] == "00:13:21"


def test_sans_transcription_rien_n_est_fait(corpus):
    import common

    common.transcript_path_for(SOURCE, GUID).unlink()
    _reco(corpus, "ubm-1")

    bilan = cc.caler_episode(SOURCE, GUID, apply=True)

    assert bilan.erreurs and not bilan.noms


def test_le_resume_cite_chaque_nom_et_compte_les_minutages():
    bilan = cc.Bilan(GUID, minutages=[("ubm-1", "00:13:21", "00:28:54")],
                     noms=[("ubm-1", "Camelot", "Kaamelott"), ("ubm-2", "Aurel San", "Orelsan")])
    assert cc.resume(bilan) == ("Noms rétablis dans les citations : Camelot → Kaamelott ; "
                                "Aurel San → Orelsan.\n1 minutage(s) recalé(s) sur la citation.")
    assert cc.resume(cc.Bilan(GUID)) == ""
