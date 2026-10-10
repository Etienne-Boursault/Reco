"""Tests de la passe des jeux sans studio : Wikidata, garde-fous, Steam, passe.

Les entités reprennent, réduites, les réponses réelles du 2026-10-10 : Dofus
(Q1139866, site `http://www.dofus.com/`, Steam 254300 retiré de la vente en
France) ; les trois jeux vidéo « Catan » ; le plateau Q17271, qui n'a
« Catan » qu'en alias.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import jeux_wikidata as jw
from _liens_fakes import ecrire_reco, lire
from boutique_links import BoutiqueInjoignable
from wikidata_links import WikidataInjoignable


def _entite(label_fr="", label_en="", natures=("Q7889",), site="", steam="",
            alias=(), wikis=("frwiki",)):
    claims = {"P31": [{"mainsnak": {"datavalue": {"value": {"id": q}}}} for q in natures]}
    if site:
        claims["P856"] = [{"mainsnak": {"datavalue": {"value": site}}}]
    if steam:
        claims["P1733"] = [{"mainsnak": {"datavalue": {"value": steam}}}]
    labels = {k: {"value": v} for k, v in (("fr", label_fr), ("en", label_en)) if v}
    return {"labels": labels, "aliases": {"fr": [{"value": a} for a in alias]},
            "claims": claims, "sitelinks": {w: {"title": label_fr} for w in wikis}}


DOFUS = _entite("Dofus", "Dofus", natures=("Q7889", "Q112144412"),
                site="http://www.dofus.com/", steam="254300")
DOFUS_ARENA = _entite("Arena", "Arena")
PLATEAU_CATAN = _entite("Les Colons de Catane", "The Settlers of Catan",
                        natures=("Q131436",), alias=("Catan",))


# ===== sélection ============================================================
def test_seuls_les_jeux_sans_studio_sont_servis():
    assert jw.servie({"types": ["jeu"]})
    assert jw.servie({"types": ["jeu"], "creator": "  "})
    assert not jw.servie({"types": ["jeu"], "creator": "Ankama"})
    assert not jw.servie({"types": ["livre"]})


# ===== lecture des entités ==================================================
def test_noms_et_valeurs():
    assert jw.noms(PLATEAU_CATAN, alias=False) == {"les colons de catane",
                                                    "the settlers of catan"}
    assert "catan" in jw.noms(PLATEAU_CATAN, alias=True)
    assert jw.valeurs(DOFUS, "P31") == ["Q7889", "Q112144412"]
    assert jw.valeurs({"claims": {"P1": [{"mainsnak": {}}]}}, "P1") == []


def test_entites_cherche_par_nature_puis_lit_le_detail(monkeypatch):
    appels = []

    def faux_get(_session, params):
        appels.append(params)
        if params["action"] == "query":
            return {"query": {"search": [{"title": "Q1139866"}, {"title": "Lexème"}]}}
        return {"entities": {"Q1139866": DOFUS, "Q2": {"missing": ""}}}

    monkeypatch.setattr(jw, "_get", faux_get)

    trouvees = jw.entites(object(), "Dofus", ("Q131436", "Q142714"))

    assert list(trouvees) == ["Q1139866"]
    assert appels[0]["srsearch"] == "Dofus haswbstatement:P31=Q131436|P31=Q142714"
    assert "sitelinks" in appels[1]["props"]


def test_entites_sans_resultat_ne_lit_rien(monkeypatch):
    monkeypatch.setattr(jw, "_get", lambda *_a: {"query": {"search": []}})
    assert jw.entites(object(), "Rien", ("Q7889",)) == {}


# ===== verdict ==============================================================
@pytest.mark.parametrize("jeux,homonymes,raison", [
    ({}, {}, "no-entity"),
    ({"Q2": DOFUS_ARENA}, {}, "no-entity"),
    ({"Q1": _entite("Catan"), "Q2": _entite(label_en="Catan")}, {}, "ambiguous"),
    ({"Q1": _entite("Catan", natures=("Q4393107",))}, {}, "type-incompatible"),
    ({"Q1": _entite("Catan", wikis=("dewiki",))}, {}, "no-wikipedia-article"),
    ({"Q1": _entite("Catan")}, {"Q17271": PLATEAU_CATAN}, "tabletop-homonym"),
    ({"Q1139866": DOFUS, "Q2": DOFUS_ARENA}, {}, "ok"),
])
def test_verdict(jeux, homonymes, raison):
    assert jw.verdict("Catan" if "Q1" in jeux else "Dofus", jeux, homonymes)[0] == raison


# ===== resoudre =============================================================
def _resoudre(monkeypatch, jeux, homonymes=None, fiche=None, reco=None):
    def fausses_entites(_session, _titre, natures):
        return jeux if natures == (jw.NATURE_JEU_VIDEO,) else (homonymes or {})

    monkeypatch.setattr(jw, "entites", fausses_entites)
    if isinstance(fiche, Exception):
        def panne(*_a):
            raise fiche
        monkeypatch.setattr(jw, "steam_fiche", panne)
    else:
        monkeypatch.setattr(jw, "steam_fiche", lambda _s, _appid: fiche)
    return jw.resoudre(reco or {"title": "Dofus", "links": []}, session=object())


def test_dofus_site_pose_steam_hors_vente(monkeypatch):
    """254300 répond `success: false` en France : le site seul."""
    resolution = _resoudre(monkeypatch, {"Q1139866": DOFUS}, fiche=None)

    assert resolution.raison == "ok" and resolution.qid == "Q1139866"
    assert [lien.as_link() for lien in resolution.liens] == [{
        "kind": "official", "ethics": "indie", "label": "Site officiel",
        "url": "http://www.dofus.com/"}]
    assert "hors vente" in resolution.detail


def test_steam_en_vente_ajoute_le_lien(monkeypatch):
    resolution = _resoudre(monkeypatch, {"Q1139866": DOFUS}, fiche={"type": "game"})
    assert [lien.url for lien in resolution.liens] == [
        "http://www.dofus.com/", "https://store.steampowered.com/app/254300/"]
    assert resolution.liens[1].kind == "buy"


def test_une_bande_son_nest_pas_le_jeu(monkeypatch):
    resolution = _resoudre(monkeypatch, {"Q1139866": DOFUS}, fiche={"type": "music"})
    assert [lien.label for lien in resolution.liens] == ["Site officiel"]


def test_steam_injoignable_garde_le_site(monkeypatch):
    resolution = _resoudre(monkeypatch, {"Q1139866": DOFUS},
                           fiche=BoutiqueInjoignable("HTTP 503"))
    assert resolution.raison == "ok" and "steam : HTTP 503" in resolution.detail


def test_rien_de_neuf_quand_le_site_est_deja_pose(monkeypatch):
    reco = {"title": "Dofus", "links": [{"url": "https://www.dofus.com/fr"}]}
    resolution = _resoudre(monkeypatch, {"Q1139866": DOFUS}, reco=reco)
    assert resolution.raison == "no-new-link" and resolution.liens == ()


def test_un_refus_ne_pose_rien(monkeypatch):
    resolution = _resoudre(monkeypatch, {"Q1": _entite("Dofus")},
                           homonymes={"Q9": _entite("Dofus", natures=("Q131436",))})
    assert resolution.raison == "tabletop-homonym" and resolution.detail == "Q9"


def test_un_jeu_sans_site_ni_steam(monkeypatch):
    resolution = _resoudre(monkeypatch, {"Q1": _entite("Dofus", site="ftp://x")})
    assert resolution.raison == "no-new-link"


def test_wikidata_injoignable(monkeypatch):
    def panne(*_a):
        raise WikidataInjoignable("429")

    monkeypatch.setattr(jw, "entites", panne)
    resolution = jw.resoudre({"title": "Dofus"}, session=object())
    assert resolution.raison == "http-error" and resolution.detail == "429"


# ===== passe et ligne de commande ===========================================
def test_run_ecrit_le_site(tmp_path: Path, monkeypatch):
    chemin = ecrire_reco(tmp_path, "src", {"id": "j-1", "title": "Dofus", "types": ["jeu"],
                                           "status": "validated", "links": []})
    ecrire_reco(tmp_path, "src", {"id": "j-2", "title": "Hades", "types": ["jeu"],
                                  "creator": "Supergiant", "status": "validated"})
    monkeypatch.setattr(jw, "entites", lambda _s, _t, natures:
                        {"Q1139866": DOFUS} if natures == (jw.NATURE_JEU_VIDEO,) else {})
    monkeypatch.setattr(jw, "steam_fiche", lambda *_a: None)

    rapport = jw.run(root=tmp_path, source="src", apply=True, sleep=0)

    assert rapport.vues == 1 and rapport.servies == {"j-1"}
    assert lire(chemin)["links"][0]["label"] == "Site officiel"


def test_main(tmp_path: Path, monkeypatch):
    appels = []
    monkeypatch.setattr(jw, "run", lambda **kw: appels.append(kw) or jw.RapportWikidata())
    assert jw.main(["--root", str(tmp_path), "--ids", "j-1", "--apply"]) == 0
    assert appels[0]["root"] == tmp_path and appels[0]["ids"] == {"j-1"}
