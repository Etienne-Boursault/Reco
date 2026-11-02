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


def test_senscritique_evoquees_recoit_les_seules_citations():
    items = {**ITEMS, "e": {"id": "e", "title": "Une BD citée", "types": ["livre"]},
             "f": {"id": "f", "title": "Citée et recommandée", "types": ["film"]}}
    mentions = [mention("m1", "a", "00:01:00"), mention("m2", "d", "00:02:00", kind="citation"),
                mention("m3", "e", "00:03:00", kind="citation"), mention("m4", "f", "00:04:00", kind="citation"),
                mention("m5", "f", "00:05:00"), mention("m6", "d", "00:06:00", kind="citation")]
    etat = {"listes": {"film": {"id": 1, "traitees": [], "ajoutees": []}},
            "evoquees": {"film": {"id": 11, "ajoutees": []},
                         "livre": {"id": 13, "traitees": [], "ajoutees": []},
                         "bd": {"id": 14, "ajoutees": ["e"]}}}
    sortie = re_.senscritique(EP, mentions, items, etat, famille="evoquees")
    # « f » est aussi recommandée dans l'épisode : elle va dans les recommandées, pas ici ;
    # « e » est déjà dans la liste des BD, même classée « livre » sur le site.
    assert sortie["film"]["oeuvres"] == []
    assert [o["fiche"] for o in sortie["livre"]["oeuvres"]] == ["d"]
    assert sortie["livre"]["liste"] == 13
    recommandees = re_.senscritique(EP, mentions, items, etat)
    assert [o["fiche"] for o in recommandees["film"]["oeuvres"]] == ["a", "f"]


def test_senscritique_sans_famille_evoquees_dans_l_etat():
    assert re_.senscritique(EP, [], ITEMS, {"listes": {}}, famille="evoquees") == {}


def test_reporter_senscritique_note_les_examinees_et_relit_les_listes():
    etat = {"listes": {"film": {"id": 1, "url": "https://sc/l1", "traitees": ["z"], "ajoutees": []}},
            "evoquees": {"livre": {"id": 13, "url": "https://sc/l13", "ajoutees": []},
                         "bd": {"id": 14, "ajoutees": ["e"]}}}
    plan = {"senscritique": {"film": {"liste": 1, "oeuvres": [{"fiche": "a"}, {"fiche": "z"}]}},
            "senscritiqueEvoquees": {"livre": {"liste": 13, "oeuvres": [{"fiche": "d"}]}}}
    lues = {"https://sc/l1": ["a"], "https://sc/l13": ["d", "x"]}
    re_.reporter_senscritique(etat, plan, lues.__getitem__)
    assert etat["listes"]["film"]["traitees"] == ["a", "z"]
    assert etat["listes"]["film"]["ajoutees"] == ["a"]
    assert etat["evoquees"]["livre"] == {"id": 13, "url": "https://sc/l13", "ajoutees": ["d", "x"], "traitees": ["d"]}
    assert etat["evoquees"]["bd"]["ajoutees"] == ["e"]


def test_relire_liste_suit_les_pages_jusqu_a_la_derniere():
    pages = {1: "oeuvre/aaaaaaaa/ unebonnere.co/un-bon-moment/oeuvre/11111111/ x "
                "unebonnere.co/un-bon-moment/oeuvre/22222222/ unebonnere.co/un-bon-moment/oeuvre/11111111/",
             2: "unebonnere.co/un-bon-moment/oeuvre/33333333/",
             3: "unebonnere.co/un-bon-moment/oeuvre/33333333/"}

    class Session:
        def get(self, url, headers, timeout):
            n = int(url.rsplit("=", 1)[1])
            return type("R", (), {"text": pages.get(n, "")})()

    assert re_.relire_liste("https://sc/l1", Session()) == ["11111111", "22222222", "33333333"]


def test_musique_ajoute_en_fin_sans_doublon_de_chanson():
    etat = {"Saison 6": {"id": "p6", "titres": ["t1", "t2"]}}
    cles = {"t1": "a|x", "t2": "b|x", "t3": "c|x", "t4": "a|x", "t5": "c|x"}
    plan, alertes = re_.musique({"Saison 6": ["t2", "t3", "t4", "t5"]}, etat, cles.get)
    assert plan == {"Saison 6": {"id": "p6", "ajouts": ["t3"]}}
    assert alertes == []


def test_musique_signale_une_playlist_a_creer():
    plan, alertes = re_.musique({"Saison 7": ["t1"]}, {}, str)
    assert plan == {} and "Saison 7" in alertes[0]


def test_spotify_manquants_musique_et_podcasts_sans_lien():
    items = {**ITEMS,
             "e": {"id": "e", "title": "Noor", "types": ["artiste"]},
             "f": {"id": "f", "title": "Un podcast", "types": ["podcast"], "creator": "Une Voix"},
             "g": {"id": "g", "title": "Un album", "types": ["album"]},
             "h": {"id": "h", "title": "Un magicien", "types": ["artiste"]},
             "162d3378": {"id": "162d3378", "title": "Greer Barnes", "types": ["artiste"]}}
    mentions = [mention("m1", "e", "00:01:00", kind="citation"), mention("m2", "f", "00:02:00"),
                mention("m3", "g", "00:03:00"), mention("m4", "a", "00:04:00"),
                mention("m5", "162d3378", "00:05:00"), mention("m6", "h", "00:06:00")]
    recos = {"m1": {"links": [{"url": "https://www.deezer.com/artist/1"}]},
             "m3": {"links": [{"url": "https://open.spotify.com/album/x"}]},
             "m5": {"links": [{"url": "https://www.deezer.com/artist/2"}]},
             "m6": {"links": [{"url": "https://fr.wikipedia.org/wiki/Un_magicien"}]}}
    assert re_.spotify_manquants(EP, mentions, items, recos) == [
        {"reco": "m1", "titre": "Noor", "createur": "", "onglet": "artists"},
        {"reco": "m2", "titre": "Un podcast", "createur": "Une Voix", "onglet": "podcastAndEpisodes"}]


def test_lien_spotify_canonique_en_tete_et_jamais_en_double():
    reco = {"links": [{"label": "Deezer", "url": "https://www.deezer.com/artist/1"}]}
    assert re_.lien_spotify(reco, "https://open.spotify.com/intl-fr/artist/3fgu?si=abc")
    assert reco["links"][0] == {"ethics": "neutral", "kind": "streaming", "label": "Spotify",
                                "url": "https://open.spotify.com/artist/3fgu"}
    assert not re_.lien_spotify(reco, "https://open.spotify.com/artist/autre")
    assert len(reco["links"]) == 2
    with pytest.raises(SystemExit):
        re_.lien_spotify({}, "https://www.deezer.com/artist/1")
