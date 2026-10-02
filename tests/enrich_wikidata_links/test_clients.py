"""Tests du client Wikidata : ce qu'il lit, et comment il échoue.

Aucun vrai appel : une fausse session rend des réponses réduites, copiées de ce
que l'API a réellement renvoyé le 2026-09-27. La distinction qui compte ici est
entre « rien trouvé » (un fait sur la personne) et « pas pu demander » (un fait
sur le réseau) : les confondre ferait conclure qu'un artiste est absent de
Wikidata un jour de coupure.
"""
from __future__ import annotations

import pytest
import requests

import wikidata_links as wl

# Réponse réelle réduite : l'entité du rappeur Fabe, telle que
# `wbgetentities&sites=frwiki&titles=Fabe` la rend.
REPONSE_FABE = {"entities": {"Q3063503": {
    "labels": {"fr": {"value": "Fabe"}},
    "aliases": {"fr": [{"value": "Fabien Marsaud"}]},
    "sitelinks": {"frwiki": {"title": "Fabe"}},
    "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}],
               "P2003": [{"mainsnak": {"datavalue": {"value": "fabe_officiel"}}}]},
}}}


class FausseReponse:
    def __init__(self, charge=None, status_code=200, casse=False):
        self._charge = charge if charge is not None else {}
        self.status_code = status_code
        self._casse = casse

    def json(self):
        if self._casse:
            raise ValueError("pas du JSON")
        return self._charge


class FausseSession:
    """Rend les réponses dans l'ordre, et garde la trace des appels."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.appels = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.appels.append({"url": url, "params": params or {},
                            "headers": headers or {}, "timeout": timeout})
        if not self.reponses:
            raise AssertionError("appel de trop")
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse


# ===== l'appel lui-même =====================================================
def test_lappel_porte_un_agent_explicite(monkeypatch):
    """Wikidata bannit les clients anonymes : l'agent doit être joignable."""
    monkeypatch.undo()
    session = FausseSession(FausseReponse({"ok": 1}))

    wl._get(session, {"action": "wbgetentities"})

    entetes = session.appels[0]["headers"]
    assert "reco" in entetes["User-Agent"] and "github.com" in entetes["User-Agent"]
    assert session.appels[0]["params"]["format"] == "json"
    assert session.appels[0]["timeout"] == wl.HTTP_TIMEOUT


@pytest.mark.parametrize("reponse,attendu", [
    (FausseReponse(status_code=429), "429"),
    (FausseReponse(status_code=503), "HTTP 503"),
    (FausseReponse(casse=True), "illisible"),
    (requests.ConnectionError("réseau coupé"), "injoignable"),
])
def test_une_derobade_leve_une_exception_typee(monkeypatch, reponse, attendu):
    """429, panne, réponse illisible : une seule exception, jamais un None muet."""
    monkeypatch.undo()
    session = FausseSession(reponse)

    with pytest.raises(wl.WikidataInjoignable, match=attendu):
        wl._get(session, {"action": "wbgetentities"})


# ===== recherche par titre d'article ========================================
def test_le_titre_darticle_ramene_lentite(monkeypatch):
    monkeypatch.undo()
    session = FausseSession(FausseReponse(REPONSE_FABE))

    trouvees = wl.entites_par_titres(session, ["Fabe"])

    assert set(trouvees) == {"Fabe"}
    entite = trouvees["Fabe"]
    assert entite.qid == "Q3063503"
    assert entite.natures == ("Q5",)
    assert entite.alias == ("Fabien Marsaud",)
    assert entite.valeur("P2003") == "fabe_officiel"
    assert session.appels[0]["params"]["sites"] == "frwiki"


def test_une_entite_absente_ne_rend_rien(monkeypatch):
    monkeypatch.undo()
    session = FausseSession(FausseReponse(
        {"entities": {"-1": {"missing": "", "title": "Linkee"}}}))

    assert wl.entites_par_titres(session, ["Linkee"]) == {}


def test_les_titres_passent_par_lots_de_cinquante(monkeypatch):
    """Un appel par tranche de 50 : c'est ce qui évite les limites d'appel."""
    monkeypatch.undo()
    session = FausseSession(FausseReponse({"entities": {}}),
                           FausseReponse({"entities": {}}))

    wl.entites_par_titres(session, [f"Titre {n}" for n in range(wl.LOT_MAX + 3)])

    assert len(session.appels) == 2
    assert session.appels[0]["params"]["titles"].count("|") == wl.LOT_MAX - 1


def test_un_titre_vide_ou_repete_ne_coute_pas_un_appel(monkeypatch):
    monkeypatch.undo()
    session = FausseSession(FausseReponse(REPONSE_FABE))

    wl.entites_par_titres(session, ["Fabe", "Fabe", ""])

    assert session.appels[0]["params"]["titles"] == "Fabe"


def test_lappariement_du_titre_ignore_casse_et_accents(monkeypatch):
    """L'article « Ben Mazué » répond à la reco « ben mazue »."""
    monkeypatch.undo()
    session = FausseSession(FausseReponse({"entities": {"Q1": {
        "labels": {"fr": {"value": "Ben Mazué"}},
        "sitelinks": {"frwiki": {"title": "Ben Mazué"}},
        "claims": {}}}}))

    assert "ben mazue" in wl.entites_par_titres(session, ["ben mazue"])


# ===== recherche par identifiant ============================================
def test_un_identifiant_ramene_lentite_qui_le_declare(monkeypatch):
    """`haswbstatement` puis lecture de l'entité : deux appels, un fait."""
    monkeypatch.undo()
    session = FausseSession(
        FausseReponse({"query": {"search": [{"title": "Q3063503"}]}}),
        FausseReponse(REPONSE_FABE))

    entites = wl.entites_par_identifiant(session, "P2722", "13674")

    assert [e.qid for e in entites] == ["Q3063503"]
    assert "haswbstatement:P2722=13674" in session.appels[0]["params"]["srsearch"]


def test_aucun_resultat_nappelle_pas_la_lecture(monkeypatch):
    monkeypatch.undo()
    session = FausseSession(FausseReponse({"query": {"search": []}}))

    assert wl.entites_par_identifiant(session, "P1902", "inconnu") == []
    assert len(session.appels) == 1


def test_deux_entites_pour_un_identifiant_sont_toutes_rendues(monkeypatch):
    """Incohérence de Wikidata : on ne tranche pas, le verdict refusera."""
    monkeypatch.undo()
    session = FausseSession(
        FausseReponse({"query": {"search": [{"title": "Q1"}, {"title": "Q2"}]}}),
        FausseReponse({"entities": {
            "Q1": {"labels": {}, "claims": {}},
            "Q2": {"labels": {}, "claims": {}}}}))

    assert len(wl.entites_par_identifiant(session, "P2722", "42")) == 2


def test_les_resultats_qui_ne_sont_pas_des_entites_sont_ignores(monkeypatch):
    """La recherche peut rendre des pages de discussion : seuls les Q comptent."""
    monkeypatch.undo()
    session = FausseSession(FausseReponse(
        {"query": {"search": [{"title": "Lexeme:L1"}, {"title": "Property:P9"}]}}))

    assert wl.entites_par_identifiant(session, "P2722", "42") == []


# ===== lecture d'une réponse ================================================
def test_une_valeur_sans_donnee_ne_casse_pas_la_lecture():
    """Un énoncé « valeur inconnue » n'a pas de `datavalue`."""
    entite = wl.entite_depuis_json("Q1", {"claims": {
        "P856": [{"mainsnak": {"snaktype": "somevalue"}},
                 {"mainsnak": {"datavalue": {"value": "https://exemple.fr/"}}}]}})

    assert entite.valeur("P856") == "https://exemple.fr/"


def test_le_libelle_anglais_sert_de_repli():
    entite = wl.entite_depuis_json("Q1", {"labels": {"en": {"value": "Someone"}}})

    assert entite.label == "Someone"
    assert entite.valeur("P31") is None


def test_une_entite_dont_larticle_differe_nest_pas_appariee(monkeypatch):
    """Garde-fou : l'entité rendue doit porter L'ARTICLE demandé.

    Wikidata peut rendre une entité voisine (redirection, homonymie) : si son
    `frwiki` n'est pas celui qu'on a demandé, on ne l'apparie pas — sinon le
    « titre exact » cesserait d'être exact.
    """
    monkeypatch.undo()
    session = FausseSession(FausseReponse({"entities": {"Q9": {
        "labels": {"fr": {"value": "Autre chose"}},
        "sitelinks": {"frwiki": {"title": "Autre chose"}},
        "claims": {}}}}))

    assert wl.entites_par_titres(session, ["Fabe"]) == {}


def test_une_entite_supprimee_entre_les_deux_appels_est_ignoree(monkeypatch):
    """La recherche la cite, la lecture la dit absente : on n'en fait rien."""
    monkeypatch.undo()
    session = FausseSession(
        FausseReponse({"query": {"search": [{"title": "Q1"}]}}),
        FausseReponse({"entities": {"Q1": {"missing": ""}}}))

    assert wl.entites_par_identifiant(session, "P2722", "42") == []
