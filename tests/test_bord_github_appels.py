"""Tests de `tools/bord_github.py`, suite : appels isolés, jeton refusé, exécutions sautées.

Tour 1 de la PR 3 (E1, F3, F5). Les outils viennent de `test_bord_github` ; le fichier est coupé
parce que l'autre atteignait le plafond de 500 lignes.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

import bord_github as bg
from test_bord_github import (
    DEPOT,
    JETON,
    MAINTENANT,
    _cache,
    _course,
    _json,
    _pr,
    _serveur,
    _tout,
)


@pytest.fixture(autouse=True)
def bord(tmp_path, monkeypatch):
    d = tmp_path / "bord"
    monkeypatch.setenv("RECO_BORD_DIR", str(d))
    monkeypatch.setenv("RECO_GITHUB_TOKEN", JETON)
    monkeypatch.setattr(bg, "_depot", lambda: DEPOT)
    return d


def _execs(*conclusions):
    return {"workflow_runs": [{"id": 20 + i, "conclusion": c, "updated_at": "2026-11-28T09:00:00Z"}
                              for i, c in enumerate(conclusions)]}


def test_le_dernier_deploiement_saute_les_executions_skipped(monkeypatch, bord):
    # `deploy.yml` suit `workflow_run` : il est sauté quand la CI échoue (F5 du tour 1).
    _serveur(monkeypatch, *_tout(deploiement=_execs("skipped", "skipped", "failure", "success")))
    bg.rafraichir(maintenant=MAINTENANT)
    deploiement = _cache(bord)["github"]["donnees"]["deploiement"]
    assert deploiement["conclusion"] == "failure" and deploiement["adresse"].endswith("/runs/22")


def test_que_des_executions_skipped_gardent_la_plus_recente(monkeypatch, bord):
    _serveur(monkeypatch, *_tout(deploiement=_execs("skipped", "skipped")))
    bg.rafraichir(maintenant=MAINTENANT)
    deploiement = _cache(bord)["github"]["donnees"]["deploiement"]
    assert deploiement["conclusion"] == "skipped" and deploiement["adresse"].endswith("/runs/20")


# ---- Un appel en panne ne perd que son bloc (E1 du tour 1) -------------------------
def test_une_reussite_complete_n_a_aucune_panne_ni_jeton_refuse(monkeypatch, bord):
    _serveur(monkeypatch, *_tout())
    bg.rafraichir(maintenant=MAINTENANT)
    donnees = _cache(bord)["github"]["donnees"]
    assert donnees["pannes"] == {} and donnees["jeton"] is None


def test_un_appel_en_panne_ne_perd_que_son_bloc(monkeypatch, bord):
    _serveur(monkeypatch, _json([_pr(1, "contenu/g")]), (500, {}, b"{}"), _json(_course()),
             _json(_course(ident=8)))
    assert bg.rafraichir(maintenant=MAINTENANT) == "ok"
    entree = _cache(bord)["github"]
    donnees = entree["donnees"]
    assert entree["lu"] == "2026-11-28T09:30:00+00:00" and entree["detail"] is None
    assert donnees["fusionnees"] is None                   # inconnu, jamais « aucune »
    assert donnees["ouvertes"]["episodes"][0]["numero"] == 1
    assert donnees["ci"]["conclusion"] == "success" and donnees["deploiement"] is not None
    assert donnees["pannes"] == {"fusionnees": {"etat": "panne", "detail": "HTTP 500"}}


def test_la_limite_de_debit_d_un_appel_ne_perd_que_son_bloc(monkeypatch, bord):
    _serveur(monkeypatch, _json([]), _json({}, 403, {"X-RateLimit-Remaining": "0"}),
             _json(_course()), OSError(f"coupé {JETON}"))
    assert bg.rafraichir(maintenant=MAINTENANT) == "ok"
    donnees = _cache(bord)["github"]["donnees"]
    assert donnees["pannes"] == {"fusionnees": {"etat": "limite", "detail": "HTTP 403"},
                                 "deploiement": {"etat": "panne", "detail": "OSError"}}
    assert donnees["ouvertes"]["episodes"] == [] and donnees["ci"] is not None
    assert donnees["fusionnees"] is None and donnees["deploiement"] is None
    assert JETON not in json.dumps(_cache(bord))


def test_quand_tous_les_appels_echouent_l_etat_est_celui_de_l_echec_et_les_donnees_restent(
        monkeypatch, bord):
    _serveur(monkeypatch, *_tout(ouvertes=[_pr(1, "contenu/g")]))
    bg.rafraichir(maintenant=MAINTENANT)
    _serveur(monkeypatch, *[_json({}, 429)] * 4)
    assert bg.rafraichir(maintenant=MAINTENANT + timedelta(minutes=11)) == "limite"
    entree = _cache(bord)["github"]
    assert (entree["etat"], entree["detail"]) == ("limite", "HTTP 429")
    assert entree["donnees"]["ouvertes"]["episodes"][0]["numero"] == 1   # celles d'avant
    assert "pannes" in entree["donnees"] and entree["donnees"]["pannes"] == {}


# ---- Un jeton refusé (F3 du tour 1) ---------------------------------------------
def test_un_jeton_refuse_repete_l_appel_sans_jeton_et_le_dit(monkeypatch, bord):
    faux = _serveur(monkeypatch, _json({"message": "Bad credentials"}, 401),
                    *_tout(ouvertes=[_pr(1, "contenu/g")]))
    assert bg.rafraichir(maintenant=MAINTENANT) == "ok"
    autorisations = [en_tetes.get("Authorization") for _, en_tetes in faux.requetes]
    assert autorisations == [f"Bearer {JETON}", None, None, None, None]   # plus de jeton ensuite
    entree = _cache(bord)["github"]
    donnees = entree["donnees"]
    assert donnees["jeton"] == "refuse" and donnees["pannes"] == {}
    assert donnees["ouvertes"]["episodes"][0]["numero"] == 1
    assert JETON not in json.dumps(entree)


def test_un_401_sans_jeton_n_est_pas_repete(monkeypatch, bord):
    monkeypatch.delenv("RECO_GITHUB_TOKEN")
    faux = _serveur(monkeypatch, *[_json({}, 401)] * 4)
    assert bg.rafraichir(maintenant=MAINTENANT) == "panne"
    assert len(faux.requetes) == 4 and _cache(bord)["github"]["detail"] == "HTTP 401"
