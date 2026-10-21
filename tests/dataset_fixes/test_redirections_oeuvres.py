"""Tests de `tools/redirections_oeuvres.py` et de son branchement dans les
outils de fusion : une fiche supprimee doit laisser une adresse qui redirige.
"""
from __future__ import annotations

import json
from pathlib import Path

import common
import fusionner_doublons_cures as fdc
import redirections_oeuvres as ro

A = "/ubm/oeuvre/a"
B = "/ubm/oeuvre/b"
C = "/ubm/oeuvre/c"


def test_ajouter_raccourcit_les_chaines():
    """A -> B, puis B fusionne dans C : A doit pointer C directement."""
    table = {A: B}
    ro.ajouter(table, B, C)
    assert table == {A: C, B: C}


def test_ajouter_retire_une_redirection_depuis_le_survivant():
    """Une fiche qui redevient survivante ne doit plus rediriger ailleurs."""
    table = {C: A}
    ro.ajouter(table, A, C)
    assert table == {A: C}


def test_noter_fusion_ecrit_a_cote_du_dossier_items(tmp_path: Path):
    perdant = tmp_path / "items" / "ubm" / "a.json"
    perdant.parent.mkdir(parents=True)
    perdant.write_text("{}", encoding="utf-8")

    assert ro.noter_fusion(perdant, "b") is True
    fichier = tmp_path / ro.NOM_FICHIER
    assert json.loads(fichier.read_text(encoding="utf-8")) == {A: B}


def test_sans_source_dans_le_chemin_rien_n_est_ecrit(tmp_path: Path):
    plat = tmp_path / "items" / "a.json"
    hors = tmp_path / "ailleurs" / "a.json"
    assert ro.noter_fusion(plat, "b") is False
    assert ro.noter_fusion(hors, "b") is False
    assert not (tmp_path / ro.NOM_FICHIER).exists()


def test_la_fusion_curee_note_la_redirection(tmp_path: Path, monkeypatch):
    items = tmp_path / "items"
    (items / "ubm").mkdir(parents=True)
    (tmp_path / "mentions").mkdir()
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(common, "MENTIONS_DIR", tmp_path / "mentions")
    for ident in ("a", "b"):
        (items / "ubm" / f"{ident}.json").write_text(
            json.dumps({"id": ident, "title": "Meme titre", "types": ["film"]}),
            encoding="utf-8")

    groupe = fdc.Groupe(survivant="b", perdants=("a",), titre="Meme titre",
                        raison="test")
    fdc.executer((groupe,), apply=True)

    assert not (items / "ubm" / "a.json").exists()
    table = json.loads((tmp_path / ro.NOM_FICHIER).read_text(encoding="utf-8"))
    assert table == {A: B}
