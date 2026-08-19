"""Tests de `tools/nettoyer_type_autre.py`.

CE QUE « AUTRE » VEUT DIRE, ET NE VEUT PAS DIRE
-----------------------------------------------
`autre` est le type de repli : l'oeuvre n'entre dans aucune des treize
categories du corpus. Il a un sens QUAND IL EST SEUL.

Accole a un vrai type, il ne dit plus rien : « Bref » porte
`types: ['autre', 'serie']` — c'est une serie, et « autre » n'ajoute aucune
information. Pire, il en retire : la carte de galerie prend `types[0]` comme
type primaire, et « autre » passe en tete par ordre alphabetique. La page
`/series` affichait donc le badge « AUTRE » sur « Bref », « Succession »,
« Iris », « Cher Journal » et « Genre Humaine » — signale a la relecture du
2026-08-19.

174 documents etaient dans ce cas : 161 items et 13 recos.

CE QUE CET OUTIL NE FAIT PAS
----------------------------
Il ne touche pas aux 400 documents dont `autre` est le SEUL type. Leur donner
une categorie demande de savoir ce qu'est l'oeuvre, ce qu'aucune regle ne
peut deduire — c'est un travail de curation, pas de nettoyage.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import nettoyer_type_autre as nta


@pytest.fixture
def racines(tmp_path: Path, monkeypatch):
    recos = tmp_path / "recos"
    items = tmp_path / "items"
    recos.mkdir()
    items.mkdir()
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    monkeypatch.setattr(df, "RECOS_DIR", recos)
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(df, "ITEMS_DIR", items)
    return recos, items


# ===== Le nettoyage ========================================================
def test_autre_disparait_quand_un_vrai_type_existe():
    doc = {"id": "x", "title": "Bref", "types": ["autre", "serie"]}
    changes = nta.transform(doc)
    assert doc["types"] == ["serie"]
    assert [c.field for c in changes] == ["types"]


def test_l_ordre_des_autres_types_est_PRESERVE():
    """La carte affiche `types[0]` : reordonner changerait le badge affiche."""
    doc = {"id": "x", "title": "T", "types": ["video", "autre", "podcast"]}
    nta.transform(doc)
    assert doc["types"] == ["video", "podcast"]


def test_plusieurs_vrais_types_survivent_tous():
    doc = {"id": "x", "title": "T", "types": ["autre", "film", "serie"]}
    nta.transform(doc)
    assert doc["types"] == ["film", "serie"]


# ===== Ce qu'il refuse de faire ============================================
def test_autre_SEUL_est_conserve():
    """C'est son seul emploi legitime : l'oeuvre n'entre dans aucune
    categorie. Le retirer laisserait `types` vide, que le schema refuse
    (`min(1)`), et ferait echouer le build."""
    doc = {"id": "x", "title": "T", "types": ["autre"]}
    assert nta.transform(doc) == []
    assert doc["types"] == ["autre"]


def test_un_document_sans_autre_n_est_pas_touche():
    doc = {"id": "x", "title": "T", "types": ["serie"]}
    assert nta.transform(doc) == []


def test_un_document_sans_types_ne_fait_pas_lever():
    assert nta.transform({"id": "x", "title": "T"}) == []


def test_des_types_mal_formes_ne_font_pas_lever():
    for mauvais in ("serie", 42, None, {}):
        assert nta.transform({"id": "x", "types": mauvais}) == [], mauvais


def test_les_doublons_sont_retires_au_passage():
    doc = {"id": "x", "title": "T", "types": ["serie", "autre", "serie"]}
    nta.transform(doc)
    assert doc["types"] == ["serie"]


def test_la_passe_est_idempotente():
    doc = {"id": "x", "title": "T", "types": ["autre", "serie"]}
    nta.transform(doc)
    assert nta.transform(doc) == []


# ===== CLI =================================================================
def test_main_traite_recos_ET_items(racines):
    recos, items = racines
    (recos / "a.json").write_text(json.dumps(
        {"id": "a", "title": "T", "types": ["autre", "film"]}), encoding="utf-8")
    (items / "b.json").write_text(json.dumps(
        {"id": "b", "title": "T", "types": ["autre", "serie"]}), encoding="utf-8")
    assert nta.main(["--apply"]) == 0
    assert json.loads((recos / "a.json").read_text(encoding="utf-8"))["types"] == ["film"]
    assert json.loads((items / "b.json").read_text(encoding="utf-8"))["types"] == ["serie"]


def test_main_dry_run_n_ecrit_pas(racines):
    _, items = racines
    p = items / "b.json"
    p.write_text(json.dumps({"id": "b", "title": "T", "types": ["autre", "serie"]}),
                 encoding="utf-8")
    avant = p.read_text(encoding="utf-8")
    assert nta.main([]) == 0
    assert p.read_text(encoding="utf-8") == avant
