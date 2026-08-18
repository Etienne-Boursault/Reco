"""Tests de `tools/purge_flags_attribution.py`.

POURQUOI CET OUTIL EXISTE
-------------------------
Le drapeau `attribution_suspect` a ete pose par la review automatique entre le
7 et le 18 juillet 2026, quand `recommendedBy` etait vide et que l'agent ne
savait pas qui recommandait. L'editeur du site a ensuite fait une passe
MANUELLE, un cas a la fois, et a renseigne le nom (commits « validations
manuelles de la session », « reviews d'Etienne via le serveur live »).

Le drapeau est reste. Resultat : 344 fiches paraissent porter une attribution
douteuse alors qu'un humain a tranche chacune. Le 2026-08-18, cette lecture
erronee a fait classer ces 344 fiches en priorite n°1 d'un backlog — l'audit
suivant retomberait dans le meme piege.

CE QUE L'OUTIL NE FAIT PAS
--------------------------
Il n'EFFACE pas : il deplace le drapeau dans `flagsResolved`. L'ambiguite
d'origine etait reelle et reste consultable ; seule cesse la fausse alerte.

Il ne touche qu'`attribution_suspect`, seul drapeau dont la resolution se lit
sans ambiguite dans la donnee (un nom est present). `title_suspect` (545),
`duplicate_suspect` (462) et `guest_missing` (351) n'ont pas ce critere.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import purge_flags_attribution as pfa


@pytest.fixture
def recos_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "src" / "content" / "recos"
    root.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", root)
    monkeypatch.setattr(df, "RECOS_DIR", root)
    items = tmp_path / "src" / "content" / "items"
    items.mkdir(parents=True)
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(df, "ITEMS_DIR", items)
    return root


def _reco(**kw):
    base = {
        "id": "ubm-0041",
        "recommendedBy": "Hakim Jemili",
        "agentReview": {
            "flags": ["attribution_suspect"],
            "reviewedByHuman": True,
            "verdict": "validate",
        },
    }
    base.update(kw)
    return base


# ===== Le cas nominal ======================================================
def test_le_drapeau_resolu_quitte_flags():
    reco = _reco()
    changes = pfa.transform(reco)
    assert reco["agentReview"]["flags"] == []
    assert [c.field for c in changes] == ["agentReview.flags"]


def test_le_drapeau_est_CONSERVE_dans_flagsResolved():
    """L'ambiguite d'origine etait reelle : on la garde consultable."""
    reco = _reco()
    pfa.transform(reco)
    assert reco["agentReview"]["flagsResolved"] == ["attribution_suspect"]


def test_les_autres_drapeaux_restent_intacts():
    reco = _reco()
    reco["agentReview"]["flags"] = ["title_suspect", "attribution_suspect", "guest_missing"]
    pfa.transform(reco)
    assert reco["agentReview"]["flags"] == ["title_suspect", "guest_missing"]
    assert reco["agentReview"]["flagsResolved"] == ["attribution_suspect"]


# ===== Les trois refus =====================================================
def test_sans_relecture_humaine_on_ne_touche_a_rien():
    """C'est la garde essentielle : sans un humain derriere, le drapeau dit
    encore quelque chose de vrai."""
    reco = _reco()
    reco["agentReview"]["reviewedByHuman"] = None
    assert pfa.transform(reco) == []
    assert reco["agentReview"]["flags"] == ["attribution_suspect"]


def test_sans_nom_renseigne_on_ne_touche_a_rien():
    """Le nom EST la resolution. Sans lui, rien n'a ete tranche."""
    for vide in ("", "   ", None):
        reco = _reco(recommendedBy=vide)
        assert pfa.transform(reco) == [], vide
        assert reco["agentReview"]["flags"] == ["attribution_suspect"]


def test_une_reco_sans_ce_drapeau_n_est_pas_touchee():
    reco = _reco()
    reco["agentReview"]["flags"] = ["title_suspect"]
    assert pfa.transform(reco) == []
    assert "flagsResolved" not in reco["agentReview"]


def test_reviewedByHuman_doit_valoir_exactement_True():
    """Une chaine « true » ou un 1 ne sont pas une relecture : la donnee
    heritee en contient, et les accepter reviendrait a purger sur du bruit."""
    for faux in ("true", 1, "oui"):
        reco = _reco()
        reco["agentReview"]["reviewedByHuman"] = faux
        assert pfa.transform(reco) == [], faux


# ===== Donnee heritee ======================================================
def test_une_reco_sans_agentReview_ne_fait_pas_lever():
    assert pfa.transform({"id": "x"}) == []


def test_un_agentReview_mal_forme_ne_fait_pas_lever():
    for mauvais in ("texte", [], 42, None):
        assert pfa.transform({"id": "x", "agentReview": mauvais}) == [], mauvais


def test_des_flags_mal_formes_ne_font_pas_lever():
    for mauvais in ("attribution_suspect", 42, {"a": 1}):
        reco = _reco()
        reco["agentReview"]["flags"] = mauvais
        assert pfa.transform(reco) == [], mauvais


def test_flagsResolved_preexistant_est_complete_sans_doublon():
    reco = _reco()
    reco["agentReview"]["flagsResolved"] = ["attribution_suspect"]
    pfa.transform(reco)
    assert reco["agentReview"]["flagsResolved"] == ["attribution_suspect"]


def test_la_passe_est_idempotente():
    reco = _reco()
    pfa.transform(reco)
    assert pfa.transform(reco) == []
    assert reco["agentReview"]["flags"] == []


# ===== CLI =================================================================
def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_main_dry_run_n_ecrit_pas(recos_root: Path, tmp_path: Path):
    path = _write(recos_root / "s" / "a.json", _reco())
    avant = path.read_text(encoding="utf-8")
    report = tmp_path / "r.json"
    assert pfa.main(["--json", str(report)]) == 0
    assert path.read_text(encoding="utf-8") == avant


def test_main_apply_ecrit(recos_root: Path):
    path = _write(recos_root / "s" / "a.json", _reco())
    assert pfa.main(["--apply"]) == 0
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["agentReview"]["flags"] == []
    assert doc["agentReview"]["flagsResolved"] == ["attribution_suspect"]
