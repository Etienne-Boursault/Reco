"""Tests pour `tools/reseaux_episode.py` — briques pures, sans reseau ni corpus."""
from __future__ import annotations

import pytest

import reseaux_episode as re_

EP = {"guid": "yt-x", "season": 6, "number": 6, "date": "2026-10-23",
      "title": "Invitée et Invité ont un truc à dire (Un Bon Moment, S6-E06)",
      "guestsParsed": ["Invitée", "Invité"]}


def mention(mid, item, ts, statut="validated", kind="reco", qui="Navo", quote="C'est top"):
    return {"id": mid, "itemId": item, "status": statut, "kind": kind, "recommendedBy": qui, "quote": quote,
            "sourceRef": {"episodeGuid": "yt-x", "timestamp": ts}}


ITEMS = {
    "a": {"id": "a", "title": "Un film", "types": ["film"], "creator": "Une Réalisatrice", "year": 2020},
    "b": {"id": "b", "title": "Une série", "types": ["serie"]},
    "c": {"id": "c", "title": "Un café", "types": ["lieu"], "creator": "Ne doit pas sortir"},
    "d": {"id": "d", "title": "Un livre", "types": ["livre"], "creator": "Un Auteur"},
}


def test_moment_retire_les_heures_vides():
    assert re_.moment("00:01:10") == "1:10"
    assert re_.moment("00:30:19") == "30:19"
    assert re_.moment("01:15:27") == "1:15:27"
    assert re_.moment(None) == ""


def test_typo_met_des_apostrophes_typographiques():
    assert re_.typo("J'allais ") == "J’allais"


def test_trouver_episode_par_code_ou_guid():
    assert re_.trouver_episode("S6-E06", [EP]) is EP
    assert re_.trouver_episode("s6e06", [EP]) is EP
    assert re_.trouver_episode("yt-x", [EP]) is EP
    with pytest.raises(SystemExit):
        re_.trouver_episode("S6-E07", [EP])


def test_createur_plateforme_puis_rien_pour_un_lieu():
    reco = {"watchProviders": [{"label": "Amazon", "ethics": "avoid"}, {"label": "HBO Max", "ethics": "neutral"}]}
    assert re_.createur(ITEMS["b"], reco) == "Sur HBO Max"
    assert re_.createur(ITEMS["a"], reco) == "Une Réalisatrice"
    assert re_.createur(ITEMS["c"], reco) == ""
    assert re_.createur(ITEMS["b"], {}) == ""


def test_carrousel_suit_l_ordre_de_l_episode_et_ignore_l_ecarte():
    mentions = [mention("m2", "b", "01:00:00"), mention("m1", "a", "00:05:00", quote="J'adore"),
                mention("m3", "c", "00:10:00", statut="discarded")]
    ep = re_.carrousel(EP, mentions, ITEMS, {})
    assert ep["numero"] == "S6 · E06"
    assert ep["titre"] == "Invitée et Invité ont un truc à dire"
    assert ep["invites"] == ["Invitée", "Invité"]
    assert ep["lien"] == "https://unebonnere.co/un-bon-moment/episode/yt-x/"
    assert [(r["type"], r["titre"], r["moment"], r["citation"]) for r in ep["recos"]] == [
        ("Film", "Un film", "5:00", "J’adore"), ("Série", "Une série", "1:00:00", "C’est top")]


def test_senscritique_sans_citation_ni_oeuvre_deja_traitee():
    mentions = [mention("m1", "a", "00:01:00"), mention("m2", "d", "00:02:00", kind="citation"),
                mention("m3", "b", "00:03:00")]
    etat = {"listes": {"film": {"id": 1, "traitees": []}, "serie": {"id": 2, "traitees": ["b"]},
                       "livre": {"id": 3, "traitees": []}}}
    sortie = re_.senscritique(EP, mentions, ITEMS, etat)
    assert sortie["film"] == {"liste": 1, "oeuvres": [
        {"fiche": "a", "titre": "Un film", "annee": 2020, "createur": "Une Réalisatrice"}]}
    assert sortie["serie"]["oeuvres"] == [] and sortie["livre"]["oeuvres"] == []


def test_musique_ajoute_en_fin_sans_doublon_de_chanson():
    etat = {"Saison 6": {"id": "p6", "titres": ["t1", "t2"]}}
    cles = {"t1": "a|x", "t2": "b|x", "t3": "c|x", "t4": "a|x", "t5": "c|x"}
    plan, alertes = re_.musique({"Saison 6": ["t2", "t3", "t4", "t5"]}, etat, cles.get)
    assert plan == {"Saison 6": {"id": "p6", "ajouts": ["t3"]}}
    assert alertes == []


def test_musique_signale_une_playlist_a_creer():
    plan, alertes = re_.musique({"Saison 7": ["t1"]}, {}, str)
    assert plan == {} and "Saison 7" in alertes[0]
