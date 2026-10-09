"""Tests de la passe YouTube Music : pistes, chaînes, Instagram, yt-dlp, passe.

Les détails de pistes reprennent ce que yt-dlp a rendu le 2026-10-10 :
« Sauf si c'est toi » (Nq9GJGHreCM), déposée par IDOL, créditée à Carla de
Coignac et Félix Radu, rangée sous la chaîne Topic UC7AmEg3… ; la page de
celle-ci lie le nom de l'artiste à sa chaîne officielle UCQPGGM6….
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import ClassVar

import pytest

import youtube_music_links as ym
from _liens_fakes import FausseReponse, FausseSession, ecrire_reco, lire

VRAI_CHERCHER = ym.chercher
VRAI_DETAILLER = ym.detailler
TOPIC = "UC7AmEg3_lG3J8HvW01zBf9w"
OFFICIELLE = "UCQPGGM6aIyb9trL6b5OyMZg"
SAUF_SI = {"id": "Nq9GJGHreCM", "title": "Sauf si c'est toi (Adaptation de Until i found you)",
           "track": "Sauf si c'est toi (Adaptation de Until i found you)",
           "artists": ["Carla de Coignac", "Félix Radu"], "channel_id": TOPIC,
           "description": "Provided to YouTube by IDOL\n\nSauf si c'est toi · Carla de Coignac"}
PEUR = {**SAUF_SI, "id": "pdl", "track": "Peur de l'amour", "artists": ["Carla de Coignac"]}
CLIP = {**PEUR, "id": "clip", "description": "Clip officiel réalisé par…"}
MORCEAU = {"id": "ubm-3258", "title": "Sauf si c'est toi (reprise française de Until I Found You)",
           "creator": "Carla de Coignac & Félix Radu", "types": ["musique"],
           "status": "validated", "links": []}
ARTISTE = {"id": "ubm-3257", "title": "Carla de Coignac", "types": ["artiste"],
           "status": "validated", "links": []}
PAGE_TOPIC = ('"content":"Carla de Coignac, Félix Radu","commandRuns":[{"startIndex":0,'
              '"length":16,"onTap":{"innertubeCommand":{"clickTrackingParams":"CDUQ",'
              f'"commandMetadata":{{"webCommandMetadata":{{"url":"/channel/{OFFICIELLE}"')
YT_MUSIC = f"https://music.youtube.com/channel/{TOPIC}"
PAGES_ARTISTE = {
    YT_MUSIC: FausseReponse("<title>Carla de Coignac</title>"),
    f"https://www.youtube.com/channel/{TOPIC}": FausseReponse(PAGE_TOPIC),
    f"https://www.youtube.com/channel/{OFFICIELLE}/about":
        FausseReponse("q=https%3A%2F%2Finstagram.com%2Fcarladecoignac&amp;"
                      " https://www.instagram.com/youtube/"),
}


def _chercheur(entrees):
    def chercher(requete, nombre):
        chercher.requetes.append((requete, nombre))
        return entrees
    chercher.requetes = []
    return chercher


def _detailleur(*details):
    par_id = {d["id"]: d for d in details}

    def detailler(video_id):
        if video_id not in par_id:
            raise RuntimeError("ERROR: Cette vidéo n'est pas disponible")
        return par_id[video_id]
    return detailler


# ===== yt-dlp ===============================================================
class FauxYoutubeDL:
    """Double de `yt_dlp.YoutubeDL` : garde ses options et l'URL demandée."""

    vus: ClassVar[list] = []

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def extract_info(self, url, download):
        FauxYoutubeDL.vus.append((self.options, url, download))
        if "search" in url:
            return {"entries": [{"id": "a"}, None, {"id": "b"}, {"id": "c"}]}
        return {**SAUF_SI, "inutile": 1}


@pytest.fixture()
def faux_yt_dlp(monkeypatch):
    FauxYoutubeDL.vus = []
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FauxYoutubeDL))


def test_la_recherche_vise_les_titres_de_youtube_music_en_francais(faux_yt_dlp):
    assert VRAI_CHERCHER("Carla de Coignac", 2) == [{"id": "a"}, {"id": "b"}]
    options, url, download = FauxYoutubeDL.vus[0]
    assert url == "https://music.youtube.com/search?q=Carla%20de%20Coignac#songs"
    assert options["extractor_args"] == {"youtube": {"lang": ["fr"]}}
    assert options["extract_flat"] is True and download is False


def test_le_detail_ne_garde_que_ce_que_la_passe_lit(faux_yt_dlp):
    details = VRAI_DETAILLER("Nq9GJGHreCM")
    assert set(details) == {"id", "title", "description", "track", "artists", "channel_id"}
    assert FauxYoutubeDL.vus[0][0]["extractor_args"] == {"youtube": {"lang": ["fr"]}}


def test_une_video_retiree_est_ignoree():
    assert ym._details(_detailleur(), "retiree") == {}


# ===== couche pure ==========================================================
def test_la_piste_de_la_reco_est_reconnue_malgre_sa_parenthese():
    assert ym.piste_officielle(SAUF_SI, MORCEAU["title"], MORCEAU["creator"])


@pytest.mark.parametrize("details", [
    {**SAUF_SI, "description": "Clip officiel"},
    {**SAUF_SI, "track": "Sauf si c'est nous"},
    {**SAUF_SI, "track": None, "title": None},
    {**SAUF_SI, "artists": ["Quelqu'un d'autre"]},
])
def test_une_autre_video_nest_pas_la_piste(details):
    assert not ym.piste_officielle(details, MORCEAU["title"], MORCEAU["creator"])


def test_la_chaine_de_lartiste_principal_seulement():
    """« Laissez-moi danser » de Waxx et Pomme est rangée chez Waxx (mesuré)."""
    waxx = {**SAUF_SI, "artists": ["Waxx", "Pomme"], "channel_id": "UC_waxx"}
    assert ym.chaine_de_lartiste(PEUR, "Carla de Coignac") == TOPIC
    assert ym.chaine_de_lartiste(waxx, "Pomme") is None
    assert ym.chaine_de_lartiste(CLIP, "Carla de Coignac") is None
    assert ym.chaine_de_lartiste({**PEUR, "channel_id": None}, "Carla de Coignac") is None


def test_la_chaine_officielle_est_celle_du_nom_lie():
    assert ym.chaine_officielle(PAGE_TOPIC, "Carla de Coignac") == OFFICIELLE
    assert ym.chaine_officielle(PAGE_TOPIC, "Félix Radu") is None
    deux = PAGE_TOPIC + PAGE_TOPIC.replace(OFFICIELLE, "UC" + "x" * 22)
    assert ym.chaine_officielle(deux, "Carla de Coignac") is None


def test_instagram_unique():
    assert ym.instagram_unique("instagram.com%2Fcarladecoignac instagram.com/youtube") == \
        "https://www.instagram.com/carladecoignac/"
    assert ym.instagram_unique("instagram.com/a instagram.com/b") is None
    assert ym.instagram_unique("rien") is None


def test_titre_de_page():
    assert ym.titre_de_page("<title>Carla &amp; co</title>") == "Carla & co"
    assert ym.titre_de_page("") == ""


@pytest.mark.parametrize("reco,morceau", [
    ({"types": ["musique"], "creator": "X"}, True),
    ({"types": ["musique"]}, True),
    ({"types": ["artiste", "musique"], "title": "Booba", "creator": "Booba"}, False),
    ({"types": ["artiste", "musique"], "title": "Sia"}, False),
    ({"types": ["artiste", "musique"], "title": "Un titre", "creator": "Sia"}, True),
    ({"types": ["artiste"]}, False),
])
def test_morceau_ou_artiste(reco, morceau):
    assert ym.est_un_morceau(reco) is morceau


def test_servie():
    assert ym.servie({"types": ["artiste"]}) and ym.servie({"types": ["musique"]})
    assert not ym.servie({"types": ["album"]})


# ===== morceau ==============================================================
def test_le_morceau_recoit_sa_piste():
    chercheur = _chercheur([{"id": "clip", "title": "Autre chose"},
                            {"id": "Nq9GJGHreCM", "title": SAUF_SI["title"]}])

    resolution = ym.resoudre_morceau(MORCEAU, chercheur=chercheur,
                                     detailleur=_detailleur(SAUF_SI))

    assert [lien.as_link() for lien in resolution.liens] == [{
        "kind": "streaming", "ethics": "neutral", "label": "YT Music",
        "url": "https://music.youtube.com/watch?v=Nq9GJGHreCM"}]
    assert chercheur.requetes == [("Sauf si c'est toi Carla de Coignac & Félix Radu", 5)]


def test_le_morceau_sans_piste_prouvee():
    chercheur = _chercheur([{"id": "clip", "title": SAUF_SI["title"]}])
    resolution = ym.resoudre_morceau(MORCEAU, chercheur=chercheur,
                                     detailleur=_detailleur(CLIP))
    assert resolution.raison == "no-entity" and resolution.detail == "1 candidate(s)"


def test_le_morceau_sans_createur_ou_deja_servi():
    sans = {**MORCEAU, "creator": ""}
    deja = {**MORCEAU, "links": [{"url": "https://music.youtube.com/watch?v=x"}]}
    assert ym.resoudre_morceau(sans, chercheur=None, detailleur=None).raison == \
        "no-creator-to-verify"
    assert ym.resoudre_morceau(deja, chercheur=None, detailleur=None).raison == "no-new-link"


# ===== artiste ==============================================================
def _artiste(reco=ARTISTE, details=(PEUR, SAUF_SI), pages=None):
    entrees = [{"id": d["id"]} for d in details] + [{"title": "sans id"}]
    return ym.resoudre_artiste(reco, session=FausseSession(pages or PAGES_ARTISTE),
                               chercheur=_chercheur(entrees),
                               detailleur=_detailleur(*details))


def test_carla_de_coignac_recoit_sa_chaine_et_son_instagram():
    resolution = _artiste()

    assert resolution.raison == "ok" and resolution.qid == TOPIC
    assert [lien.url for lien in resolution.liens] == [
        YT_MUSIC, "https://www.instagram.com/carladecoignac/"]


def test_linstagram_deja_pose_nest_pas_cherche():
    reco = {**ARTISTE, "links": [{"url": "https://www.instagram.com/carla/"}]}
    pages = {YT_MUSIC: PAGES_ARTISTE[YT_MUSIC]}
    assert [lien.label for lien in _artiste(reco, pages=pages).liens] == ["YT Music"]


def test_seul_linstagram_manquait():
    reco = {**ARTISTE, "links": [{"url": YT_MUSIC}]}
    assert [lien.label for lien in _artiste(reco).liens] == ["Instagram"]


def test_sans_chaine_officielle_pas_dinstagram():
    pages = {**PAGES_ARTISTE, f"https://www.youtube.com/channel/{TOPIC}": FausseReponse("")}
    reco = {**ARTISTE, "links": [{"url": YT_MUSIC}]}
    resolution = _artiste(reco, pages=pages)
    assert resolution.raison == "no-new-link" and resolution.qid == TOPIC


def test_tout_est_deja_pose():
    reco = {**ARTISTE, "links": [{"url": YT_MUSIC},
                                 {"url": "https://www.instagram.com/carla/"}]}
    assert ym.resoudre_artiste(reco, session=None, chercheur=None,
                               detailleur=None).raison == "no-new-link"


def test_aucune_piste_de_lartiste():
    resolution = _artiste(details=(CLIP,))
    assert resolution.raison == "no-entity" and "1 piste" in resolution.detail


def test_deux_chaines_pour_un_nom_ambigu():
    """Al'Tarba : deux pistes « de lui » sous deux chaînes différentes (mesuré)."""
    autre = {**SAUF_SI, "id": "x", "artists": ["Carla de Coignac"], "channel_id": "UC_autre"}
    resolution = _artiste(details=(PEUR, autre))
    assert resolution.raison == "ambiguous" and "UC_autre" in resolution.detail


def test_la_page_youtube_music_doit_porter_le_nom():
    pages = {YT_MUSIC: FausseReponse("<title>undefined</title>")}
    resolution = _artiste(pages=pages)
    assert resolution.raison == "yt-music-title-mismatch" and "undefined" in resolution.detail


# ===== resoudre : aiguillage et pannes ======================================
def test_resoudre_aiguille_et_resout_les_clients_a_lappel(monkeypatch):
    monkeypatch.setattr(ym, "chercher", _chercheur([{"id": "Nq9GJGHreCM",
                                                     "title": SAUF_SI["title"]}]))
    monkeypatch.setattr(ym, "detailler", _detailleur(SAUF_SI))
    assert ym.resoudre(MORCEAU, session=FausseSession()).raison == "ok"


def test_resoudre_artiste():
    resolution = ym.resoudre(ARTISTE, session=FausseSession(PAGES_ARTISTE),
                             chercheur=_chercheur([{"id": "pdl"}]),
                             detailleur=_detailleur(PEUR))
    assert resolution.raison == "ok"


def test_une_page_injoignable_devient_une_raison():
    pages = {YT_MUSIC: FausseReponse(status_code=503)}
    resolution = ym.resoudre(ARTISTE, session=FausseSession(pages),
                             chercheur=_chercheur([{"id": "pdl"}]),
                             detailleur=_detailleur(PEUR))
    assert resolution.raison == "http-error" and "503" in resolution.detail


def test_une_recherche_en_echec_devient_une_raison():
    def panne(*_a):
        raise RuntimeError("ERROR: HTTP Error 429")

    resolution = ym.resoudre(MORCEAU, session=FausseSession(), chercheur=panne,
                             detailleur=_detailleur())
    assert resolution.raison == "http-error" and "429" in resolution.detail


# ===== passe et ligne de commande ===========================================
def test_run_ecrit_et_pose_le_cookie_de_consentement(tmp_path: Path, monkeypatch):
    chemin = ecrire_reco(tmp_path, "src", MORCEAU)
    sessions = []

    def resoudre(reco, *, session):
        sessions.append(session)
        return ym.Resolution((ym.Lien(*ym.YT_MUSIC, "https://music.youtube.com/watch?v=x"),),
                             "ok", ym.PREUVE)

    monkeypatch.setattr(ym, "resoudre", resoudre)

    rapport = ym.run(root=tmp_path, source="src", apply=True, sleep=0)

    assert rapport.servies == {"ubm-3258"}
    assert lire(chemin)["links"][0]["label"] == "YT Music"
    assert sessions[0].cookies.get("SOCS", domain=".youtube.com") == "CAI"


def test_main(tmp_path: Path, monkeypatch):
    appels = []
    monkeypatch.setattr(ym, "run", lambda **kw: appels.append(kw) or ym.RapportWikidata())
    assert ym.main(["--root", str(tmp_path), "--source", "src"]) == 0
    assert appels[0]["root"] == tmp_path and appels[0]["apply"] is False
