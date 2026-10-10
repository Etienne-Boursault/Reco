"""Tests du module réseau des plateformes vidéo : pages, Wikidata, ARTE, passe.

Les pages sont réduites à ce que le client lit : statut, URL finale (après
redirection) et titre. Les URL sont celles relevées le 2026-10-10.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import requests

import streaming_links as sl
import streaming_matching as sm
from _liens_fakes import FausseReponse, FausseSession, ecrire_reco, lire
from wikidata_links import WikidataInjoignable
from wikidata_matching import Entite, Lien

APPLE_NU = "https://tv.apple.com/fr/show/umc.cmc.3q807jzamz6a79sq9c1nco48o"
APPLE_CANONIQUE = "https://tv.apple.com/fr/show/fleabag/umc.cmc.3q807jzamz6a79sq9c1nco48o"
DISNEY_ANCIEN = "https://www.disneyplus.com/series/wp/52m6nx7HoP5F"
DISNEY_FINAL = "https://www.disneyplus.com/browse/entity-05eb6a8e-90ed-4947-8c0b-e6536cbddd5f"
PRIME = "https://www.primevideo.com/-/fr/detail/0LT1TJXTAD3TVX4QBV0QDG1BCB"
ACHARNES = Entite("Q112168983", claims={"P4983": ("154385",), "P1874": ("81447461",)})
SAMUEL_PAGE = ("<title>Samuel - Séries et fictions | ARTE</title>"
               "<p>la série d'Émilie Tronche</p>")
RC_SAMUEL = "https://www.arte.tv/fr/videos/RC-024878/samuel/"


def _a_resoudre(source, url):
    return Lien(source, "streaming", "neutral", source, sm.A_RESOUDRE + url)


# ===== pages ================================================================
def test_lappel_porte_un_agent_explicite_et_le_francais():
    session = FausseSession({"https://x": FausseReponse("ok")})

    sl._page(session, "https://x")

    entetes = session.appels[0]["headers"]
    assert "github.com" in entetes["User-Agent"] and entetes["Accept-Language"].startswith("fr")


@pytest.mark.parametrize("reponse,attendu", [
    (FausseReponse(status_code=429), "429"),
    (FausseReponse(status_code=503), "HTTP 503"),
    (requests.ConnectionError("coupé"), "injoignable"),
])
def test_une_derobade_leve_une_exception_typee(reponse, attendu):
    with pytest.raises(sl.PageInjoignable, match=attendu):
        sl._page(FausseSession({"https://x": reponse}), "https://x")


def test_un_404_est_une_reponse_pas_une_panne():
    assert sl._page(FausseSession({"https://x": FausseReponse(status_code=404)}),
                    "https://x").status_code == 404


# ===== résolution des URL déclarées =========================================
def test_apple_tv_prend_la_forme_canonique_que_le_site_declare():
    session = FausseSession({APPLE_NU: FausseReponse(url=APPLE_CANONIQUE)})
    assert sl.resoudre_url(session, _a_resoudre("apple", APPLE_NU)) == APPLE_CANONIQUE


def test_apple_tv_hors_storefront_francais_refuse():
    session = FausseSession({APPLE_NU: FausseReponse(url="https://tv.apple.com/us/show/x/umc.cmc.1")})
    assert sl.resoudre_url(session, _a_resoudre("apple", APPLE_NU)) is None


def test_disney_ancien_identifiant_reecrit_en_fr_fr():
    session = FausseSession({DISNEY_ANCIEN: FausseReponse(url=DISNEY_FINAL)})
    assert sl.resoudre_url(session, _a_resoudre("disney", DISNEY_ANCIEN)) == \
        "https://www.disneyplus.com/fr-fr/browse/entity-05eb6a8e-90ed-4947-8c0b-e6536cbddd5f"


def test_disney_redirige_ailleurs_refuse():
    session = FausseSession({DISNEY_ANCIEN: FausseReponse(url="https://www.disneyplus.com/")})
    assert sl.resoudre_url(session, _a_resoudre("disney", DISNEY_ANCIEN)) is None


def test_prime_garde_lurl_demandee_si_la_page_existe():
    session = FausseSession({PRIME: FausseReponse(url=PRIME + "?ref=x")})
    assert sl.resoudre_url(session, _a_resoudre("prime", PRIME)) == PRIME


def test_une_page_absente_ne_donne_rien():
    session = FausseSession({PRIME: FausseReponse(status_code=404)})
    assert sl.resoudre_url(session, _a_resoudre("prime", PRIME)) is None


# ===== chemin Wikidata ======================================================
def _reco(**champs):
    return {"id": "r", "title": "Fleabag", "types": ["serie"], "status": "validated",
            "externalIds": {"tmdb": "67070", "tmdbType": "tv"}, "links": [], **champs}


def test_wikidata_resout_les_liens_a_resoudre_et_note_les_pages_absentes(monkeypatch):
    entite = Entite("Q16868648", claims={
        "P4983": ("67070",), "P9751": ("umc.cmc.3q807jzamz6a79sq9c1nco48o",),
        "P14440": ("0LT1TJXTAD3TVX4QBV0QDG1BCB",), "P1267": ("20611",)})
    monkeypatch.setattr(sl, "entites_par_identifiant", lambda _s, prop, val: [entite])
    session = FausseSession({APPLE_NU: FausseReponse(url=APPLE_CANONIQUE),
                             PRIME: FausseReponse(status_code=404)})
    reco = _reco(watchProviders=[{"label": "Apple TV Store"},
                                 {"label": "Amazon Prime Video"}])

    liens, raison, qid, detail = sl._par_wikidata(reco, session)

    assert [(lien.label, lien.kind, lien.url) for lien in liens] == [
        ("Apple TV", "buy", APPLE_CANONIQUE),
        ("AlloCiné", "info", "https://www.allocine.fr/series/ficheserie_gen_cserie=20611.html")]
    assert raison == "ok" and qid == "Q16868648"
    assert "page absente : Prime Video" in detail


def test_wikidata_sans_identifiant_tmdb_ne_demande_rien(monkeypatch):
    monkeypatch.setattr(sl, "entites_par_identifiant",
                        lambda *_a: pytest.fail("aucun appel attendu"))
    liens, raison, _qid, _d = sl._par_wikidata({"externalIds": {}}, FausseSession())
    assert (liens, raison) == ([], "no-tmdb-id")


# ===== chemin ARTE ==========================================================
class SessionArte(FausseSession):
    """La recherche ARTE se distingue par son paramètre `q`."""

    def __init__(self, recherches, pages):
        super().__init__(pages)
        self.recherches = recherches

    def get(self, url, params=None, headers=None, timeout=None):
        if url == sl.ARTE_RECHERCHE:
            self.appels.append({"url": url, "params": params})
            return FausseReponse(self.recherches.get(params["q"], ""), url=url)
        return super().get(url, params, headers, timeout)


SAMUEL = {"id": "s", "title": "Samuel", "creator": "Émilie Tronche", "types": ["serie"],
          "status": "validated", "links": []}


def test_arte_trouve_ouvre_et_corrobore():
    session = SessionArte({"Samuel": '<a href="/fr/videos/RC-024878/samuel/">'},
                          {RC_SAMUEL: FausseReponse(SAMUEL_PAGE)})
    liens, raison, _ = sl._par_arte(SAMUEL, session)
    assert raison == "ok" and [lien.url for lien in liens] == [RC_SAMUEL]


def test_arte_essaie_le_titre_sans_parenthese():
    reco = {**SAMUEL, "title": "Samuel (série)", "types": ["film"]}
    session = SessionArte({"Samuel": '<a href="/fr/videos/120032-000-A/samuel/">'},
                          {"https://www.arte.tv/fr/videos/120032-000-A/samuel/":
                           FausseReponse(SAMUEL_PAGE)})
    _liens, raison, _ = sl._par_arte(reco, session)
    assert raison == "ok"
    assert [a["params"]["q"] for a in session.appels if a["url"] == sl.ARTE_RECHERCHE] == \
        ["Samuel (série)", "Samuel"]


def test_arte_deux_candidats_ambigu():
    page = ('<a href="/fr/videos/RC-000001/samuel/">'
            '<a href="/fr/videos/RC-000002/samuel/">')
    _l, raison, detail = sl._par_arte(SAMUEL, SessionArte({"Samuel": page}, {}))
    assert raison == "ambiguous" and "RC-000002" in detail


def test_arte_page_expiree():
    session = SessionArte({"Samuel": '<a href="/fr/videos/RC-024878/samuel/">'},
                          {RC_SAMUEL: FausseReponse(status_code=404)})
    assert sl._par_arte(SAMUEL, session)[1] == sm.RAISON_ARTE_INTROUVABLE


def test_arte_page_non_corroboree():
    session = SessionArte({"Samuel": '<a href="/fr/videos/RC-024878/samuel/">'},
                          {RC_SAMUEL: FausseReponse("<title>Samuel - Séries | ARTE</title>")})
    _l, raison, motif = sl._par_arte(SAMUEL, session)
    assert raison == sm.RAISON_ARTE_NON_CORROBORE and "créateur" in motif


def test_arte_rien_trouve():
    assert sl._par_arte(SAMUEL, SessionArte({}, {}))[1] == sm.RAISON_ARTE_INTROUVABLE


# ===== resoudre : les deux chemins ==========================================
def test_les_deux_chemins_se_cumulent_arte_en_tete(monkeypatch):
    netflix = Lien("netflix", "streaming", "neutral", "Netflix", "https://netflix.com/title/1")
    arte = sm.lien_arte(RC_SAMUEL)
    monkeypatch.setattr(sl, "_par_wikidata", lambda *_a: ([netflix], "ok", "Q1", ""))
    monkeypatch.setattr(sl, "_par_arte", lambda *_a: ([arte], "ok", ""))

    resolution = sl.resoudre(SAMUEL, session=FausseSession())

    assert [lien.source for lien in resolution.liens] == ["arte", "netflix"]
    assert resolution.preuve == sl.PREUVE_TMDB and resolution.qid == "Q1"


def test_arte_seul_a_sa_propre_preuve(monkeypatch):
    monkeypatch.setattr(sl, "_par_wikidata", lambda *_a: ([], "no-entity", None, ""))
    monkeypatch.setattr(sl, "_par_arte", lambda *_a: ([sm.lien_arte(RC_SAMUEL)], "ok", ""))
    assert sl.resoudre(SAMUEL, session=FausseSession()).preuve == sl.PREUVE_ARTE


def test_une_panne_de_wikidata_noublie_pas_arte(monkeypatch):
    def panne(*_a):
        raise WikidataInjoignable("429")

    monkeypatch.setattr(sl, "_par_wikidata", panne)
    monkeypatch.setattr(sl, "_par_arte", lambda *_a: ([], sm.RAISON_ARTE_INTROUVABLE, "rien"))

    resolution = sl.resoudre(SAMUEL, session=FausseSession())

    assert resolution.raison == "http-error"
    assert "wikidata : 429" in resolution.detail and "arte : rien" in resolution.detail


def test_une_panne_darte_est_signalee(monkeypatch):
    def panne(*_a):
        raise sl.PageInjoignable("HTTP 503")

    monkeypatch.setattr(sl, "_par_wikidata", lambda *_a: ([], "no-entity", None, ""))
    monkeypatch.setattr(sl, "_par_arte", panne)
    resolution = sl.resoudre(SAMUEL, session=FausseSession())
    assert resolution.raison == "http-error" and "arte : HTTP 503" in resolution.detail


def test_arte_deja_pose_nest_pas_recherche(monkeypatch):
    monkeypatch.setattr(sl, "_par_wikidata", lambda *_a: ([], "no-entity", None, ""))
    monkeypatch.setattr(sl, "_par_arte", lambda *_a: pytest.fail("ARTE déjà posé"))
    reco = {**SAMUEL, "links": [{"url": RC_SAMUEL}]}
    assert sl.resoudre(reco, session=FausseSession()).raison == "no-entity"


# ===== passe et ligne de commande ===========================================
def test_run_ecrit_les_plateformes_en_tete(tmp_path: Path, monkeypatch):
    chemin = ecrire_reco(tmp_path, "src", {**SAMUEL, "links": [
        {"label": "IMDb", "url": "https://www.imdb.com/title/tt15498808/"}]})
    monkeypatch.setattr(sl, "_par_wikidata", lambda *_a: ([], "no-entity", None, ""))
    monkeypatch.setattr(sl, "_par_arte", lambda *_a: ([sm.lien_arte(RC_SAMUEL)], "ok", ""))

    rapport = sl.run(root=tmp_path, source="src", apply=True, sleep=0)

    assert rapport.servies == {"s"}
    assert [lien["label"] for lien in lire(chemin)["links"]] == ["ARTE.tv", "IMDb"]


def test_main_lit_ses_options(tmp_path: Path, monkeypatch):
    appels = []
    monkeypatch.setattr(sl, "run", lambda **kw: appels.append(kw) or sl.RapportWikidata())

    assert sl.main(["--root", str(tmp_path), "--source", "src", "--ids", "a,b"]) == 0

    (recu,) = appels
    assert recu["root"] == tmp_path and recu["ids"] == {"a", "b"} and recu["apply"] is False


def test_main_prend_le_corpus_resolu_a_lappel(tmp_path: Path, monkeypatch):
    import common

    monkeypatch.setattr(common, "RECOS_DIR", tmp_path)
    appels = []
    monkeypatch.setattr(sl, "run", lambda **kw: appels.append(kw) or sl.RapportWikidata())
    sl.main(["--apply"])
    assert appels[0]["root"] == tmp_path and appels[0]["apply"] is True
