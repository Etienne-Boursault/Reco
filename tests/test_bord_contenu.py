"""Tests de `tools/bord_contenu.py` : sorties à venir, graphies et liens morts (tranche 3c).

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026. Tout se passe dans des
dossiers temporaires : les chemins se résolvent à l'appel (`common.RECOS_DIR`, `common.OUTPUT_DIR`,
`RECO_BORD_DIR`), donc aucun test n'écrit ni ne lit le vrai corpus. Une partie illisible se dit
« inconnu » (`None`), jamais « aucun » (F22) ; une liste coupée dit son total (F23).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import bord_contenu
import common

MAINTENANT = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
SOURCE = "un-bon-moment"


@pytest.fixture(autouse=True)
def monde(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setenv("RECO_BORD_DIR", str(tmp_path / "bord"))
    (tmp_path / "recos" / SOURCE).mkdir(parents=True)
    return tmp_path


def _reco(monde: Path, nom: str, **champs) -> None:
    doc = {"id": nom, "sourceId": SOURCE, "title": f"Titre {nom}", "status": "validated",
           "types": ["album"], **champs}
    (monde / "recos" / SOURCE / f"{nom}.json").write_text(json.dumps(doc), encoding="utf-8")


def _lire():
    return bord_contenu.lire(SOURCE, maintenant=MAINTENANT)


# ---- Sorties à venir -------------------------------------------------------
def test_les_sorties_dans_les_trente_jours_et_pas_au_dela(monde):
    _reco(monde, "a-j-plus-30", releaseDate="2026-12-28")
    _reco(monde, "b-j-plus-31", releaseDate="2026-12-29")
    _reco(monde, "c-j-moins-30", releaseDate="2026-10-29")
    _reco(monde, "d-j-moins-31", releaseDate="2026-10-28")
    _reco(monde, "e-sans-date")
    sorties = _lire()["sorties"]
    assert [(s["id"], s["jours"]) for s in sorties["liste"]] == [
        ("c-j-moins-30", -30), ("a-j-plus-30", 30)]
    assert sorties["total"] == 2 and sorties["illisibles"] == 0
    assert sorties["liste"][0] == {"id": "c-j-moins-30", "titre": "Titre c-j-moins-30",
                                   "date": "2026-10-29", "jours": -30, "relancee": False}


def test_une_reco_non_validee_ou_non_servie_ou_a_date_fausse_est_ecartee(monde):
    _reco(monde, "brouillon", releaseDate="2026-12-01", status="draft")
    _reco(monde, "film", releaseDate="2026-12-01", types=["film"])
    _reco(monde, "fausse", releaseDate="2026-02-30")
    _reco(monde, "bonne", releaseDate="2026-12-01")
    assert [s["id"] for s in _lire()["sorties"]["liste"]] == ["bonne"]


def test_la_liste_est_coupee_par_date_et_dit_son_total(monde):
    for k in range(12):
        _reco(monde, f"r{k:02d}", releaseDate=f"2026-12-{k + 1:02d}")
    sorties = _lire()["sorties"]
    assert sorties["total"] == 12
    assert len(sorties["liste"]) == bord_contenu.LISTE_MAX
    assert sorties["liste"][0]["date"] == "2026-12-01"
    assert sorties["liste"][-1]["date"] == "2026-12-10"


def test_une_reco_illisible_se_compte_et_les_autres_restent(monde):
    _reco(monde, "bonne", releaseDate="2026-12-01")
    (monde / "recos" / SOURCE / "cassee.json").write_text('{"releaseDate": ', encoding="utf-8")
    (monde / "recos" / SOURCE / "liste.json").write_text('["releaseDate"]', encoding="utf-8")
    (monde / "recos" / SOURCE / "dossier.json").mkdir()
    sorties = _lire()["sorties"]
    assert [s["id"] for s in sorties["liste"]] == ["bonne"]
    assert sorties["illisibles"] == 3


def test_pas_de_dossier_de_recos_c_est_inconnu_et_non_aucune(monde):
    (monde / "recos" / SOURCE).rmdir()
    assert _lire()["sorties"] is None


def test_aucune_sortie_annoncee_est_une_mesure(monde):
    _reco(monde, "sans-date")
    assert _lire()["sorties"] == {"liste": [], "total": 0, "illisibles": 0}


def test_une_reco_deja_relancee_est_marquee(monde):
    _reco(monde, "a", releaseDate="2026-11-20")
    _reco(monde, "b", releaseDate="2026-11-21")
    etat = monde / "output" / "pipeline" / "sorties-annoncees.json"
    etat.parent.mkdir(parents=True)
    etat.write_text(json.dumps({"relancees": [f"{SOURCE}/a"]}), encoding="utf-8")
    assert [(s["id"], s["relancee"]) for s in _lire()["sorties"]["liste"]] == [
        ("a", True), ("b", False)]


def test_un_etat_de_relance_illisible_laisse_relancee_inconnue(monde):
    _reco(monde, "a", releaseDate="2026-11-20")
    etat = monde / "output" / "pipeline" / "sorties-annoncees.json"
    etat.parent.mkdir(parents=True)
    etat.write_text("[", encoding="utf-8")
    assert _lire()["sorties"]["liste"][0]["relancee"] is None


def test_un_titre_absent_ou_trop_long_reste_sur(monde):
    _reco(monde, "a", releaseDate="2026-12-01", title=None)
    _reco(monde, "b", releaseDate="2026-12-02", title="x" * 500)
    a, b = _lire()["sorties"]["liste"]
    assert a["titre"] == "a" and len(b["titre"]) == bord_contenu.TITRE_MAX


# ---- Graphies --------------------------------------------------------------
def _registre(monde: Path, contenu) -> None:
    chemin = monde / "graphies" / "registre.json"  # conftest : `_dossier` isolé sous tmp_path
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu if isinstance(contenu, str) else json.dumps(contenu),
                      encoding="utf-8")


def test_sans_registre_il_n_y_a_aucune_graphie(monde):
    assert _lire()["graphies"] == {"total": 0, "plus_vues": [], "ecartees": 0}


def test_les_cinq_graphies_les_plus_vues_et_le_total(monde):
    _registre(monde, {"entrees": [
        {"fausse": f"f{k}", "juste": f"j{k}", "vu": k} for k in range(7)]
        + [{"fausse": "mal", "juste": ""}]})
    graphies = _lire()["graphies"]
    assert graphies["total"] == 7 and graphies["ecartees"] == 1
    assert [g["fausse"] for g in graphies["plus_vues"]] == ["f6", "f5", "f4", "f3", "f2"]
    assert graphies["plus_vues"][0] == {"fausse": "f6", "juste": "j6", "vu": 6}


def test_a_egalite_l_ordre_est_alphabetique(monde):
    _registre(monde, {"entrees": [{"fausse": "b", "juste": "x", "vu": 2},
                                  {"fausse": "a", "juste": "x", "vu": 2}]})
    assert [g["fausse"] for g in _lire()["graphies"]["plus_vues"]] == ["a", "b"]


@pytest.mark.parametrize("brut", ["{", '{"entrees": 3}', "[]"])
def test_un_registre_illisible_est_inconnu_et_non_vide(monde, brut):
    _registre(monde, brut)
    assert _lire()["graphies"] is None


# ---- Liens morts -----------------------------------------------------------
RESUME = {"date": "2026-11-24", "morts": 12, "nouveaux": 2, "inconnus": 5, "vivants": 900,
          "liste": [{"url": "https://a.example/", "reponse": "HTTP 404", "recos": ["r1"]}]}


def _liens(monde: Path, contenu) -> None:
    chemin = monde / "bord" / "liens.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu if isinstance(contenu, str) else json.dumps(contenu),
                      encoding="utf-8")


def test_le_resume_des_liens_avec_son_age(monde):
    _liens(monde, RESUME)
    assert _lire()["liens"] == {
        "date": "2026-11-24", "age": 4, "ancien": False, "morts": 12, "nouveaux": 2,
        "inconnus": 5, "vivants": 900,
        "liste": [{"url": "https://a.example/", "reponse": "HTTP 404", "recos": ["r1"]}]}


@pytest.mark.parametrize(("date", "ancien"), [("2026-11-20", False), ("2026-11-19", True)])
def test_au_dela_de_huit_jours_le_rapport_est_ancien(monde, date, ancien):
    _liens(monde, {**RESUME, "date": date})
    assert _lire()["liens"]["ancien"] is ancien


def test_pas_de_resume_c_est_inconnu(monde):
    assert _lire()["liens"] is None


@pytest.mark.parametrize("contenu", [
    "{", "[]", {**RESUME, "date": "hier"}, {**RESUME, "date": 3}, {**RESUME, "morts": "12"},
    {**RESUME, "morts": True}, {**RESUME, "liste": "x"}, {**RESUME, "liste": [3]},
    {**RESUME, "liste": [{"url": 3, "reponse": "x", "recos": []}]},
    {**RESUME, "liste": [{"url": "u", "reponse": "x", "recos": "r"}]},
    {**RESUME, "nouveaux": None}, {k: v for k, v in RESUME.items() if k != "vivants"},
])
def test_un_resume_de_forme_fausse_est_inconnu(monde, contenu):
    _liens(monde, contenu)
    assert _lire()["liens"] is None


# ---- Jamais d'exception ----------------------------------------------------
@pytest.mark.parametrize("partie", ["_sorties", "_graphies", "_liens"])
def test_une_partie_qui_plante_est_inconnue_et_les_autres_restent(monde, monkeypatch, partie):
    def plante(*_a, **_k):
        raise RuntimeError("boum")
    monkeypatch.setattr(bord_contenu, partie, plante)
    resultat = _lire()
    assert set(resultat) == {"sorties", "graphies", "liens"}
    assert resultat[partie.strip("_")] is None
    # Sans résumé de liens, `liens` est déjà inconnu ; les deux autres parties restent lues.
    assert all(resultat[p] is not None for p in ("sorties", "graphies") if "_" + p != partie)


def test_sans_horloge_donnee_lire_prend_l_heure_actuelle(monde):
    assert set(bord_contenu.lire(SOURCE)) == {"sorties", "graphies", "liens"}
