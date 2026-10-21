"""Tests de `tools/corrections_audit_2026_10.py`.

Les tables sont curees a la main : ces tests verifient ce qui en limite la
portee — une source pour chaque ligne, des types qui existent, des corrections
qui visent la fiche qui SURVIT a la fusion — puis rejouent le script entier
sur un corpus temporaire.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import corrections_audit_2026_10 as audit
import corriger_attributions_erronees as cae
from domain.item import ItemType

TYPES_VALIDES = {t.value for t in ItemType}


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    for nom in ("items", "recos", "mentions"):
        (tmp_path / nom).mkdir()
    monkeypatch.setattr(common, "ITEMS_DIR", tmp_path / "items")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    monkeypatch.setattr(common, "MENTIONS_DIR", tmp_path / "mentions")
    return tmp_path


def poser(racine: Path, dossier: str, nom: str, doc: dict) -> Path:
    chemin = racine / dossier / f"{nom}.json"
    chemin.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return chemin


def lire(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


# ===== Les tables ==========================================================
def test_chaque_correction_porte_une_preuve_ouvrable():
    for c in audit.CORRECTIONS:
        assert c.preuve.startswith("https://"), c.item_id


def test_les_types_poses_existent():
    poses = [t for c in audit.CORRECTIONS for t in c.types]
    poses += [t for g in audit.GROUPES for t in g.types]
    assert set(poses) <= TYPES_VALIDES


def test_aucune_correction_ne_vise_une_fiche_supprimee_par_la_fusion():
    """Une correction sur un perdant ne s'appliquerait jamais : la fiche
    n'existe plus quand l'etape 2 tourne."""
    perdants = {p for g in audit.GROUPES for p in g.perdants}
    assert not perdants & {c.item_id for c in audit.CORRECTIONS}


def test_une_fiche_n_est_corrigee_qu_une_fois():
    ids = [c.item_id for c in audit.CORRECTIONS]
    assert len(ids) == len(set(ids))


# ===== Le champ `types` du moteur de correction ============================
def test_types_poses_sur_le_document():
    correction = cae.Correction(item_id="zz", titre="Zaho",
                                preuve="https://exemple.fr/",
                                types=("artiste", "musique"))
    doc = {"id": "zz", "types": ["album", "artiste"]}
    assert cae._corriger_document(doc, correction) == ["types"]
    assert doc["types"] == ["artiste", "musique"]


def test_sans_types_la_correction_n_y_touche_pas():
    correction = cae.Correction(item_id="zz", titre="Zaho",
                                preuve="https://exemple.fr/")
    doc = {"id": "zz", "types": ["album"]}
    assert cae._corriger_document(doc, correction) == []
    assert doc["types"] == ["album"]


# ===== Le script entier, sur un corpus temporaire ==========================
def test_fusion_puis_alignement_des_recos(corpus: Path):
    """Joe Rogan : la fiche perdante disparait, sa mention passe au
    survivant, et sa reco prend le titre et le createur du survivant."""
    poser(corpus, "items", "0099e3e6", {
        "id": "0099e3e6", "title": "The Joe Rogan Experience",
        "types": ["podcast"], "creator": "Joe Rogan"})
    perdant = poser(corpus, "items", "0139f55a", {
        "id": "0139f55a", "title": "Joe Rogan Experience", "types": ["podcast"]})
    mention = poser(corpus, "mentions", "ubm-2457", {
        "id": "ubm-2457", "itemId": "0139f55a", "status": "validated"})
    reco = poser(corpus, "recos", "2457", {
        "id": "ubm-2457", "status": "validated",
        "title": "Joe Rogan Experience", "types": ["podcast"]})

    audit.executer(apply=True)

    assert not perdant.exists()
    assert lire(mention)["itemId"] == "0099e3e6"
    assert lire(reco)["title"] == "The Joe Rogan Experience"
    assert lire(reco)["creator"] == "Joe Rogan"
    survivant = lire(corpus / "items" / "0099e3e6.json")
    assert survivant["aliases"] == ["Joe Rogan Experience"]


def test_la_mention_en_double_est_ecartee_une_seule_fois(corpus: Path):
    chemin = poser(corpus, "mentions", "ubm-1560", {
        "id": "ubm-1560", "itemId": "8b112235", "status": "validated"})
    assert audit.ecarter_mentions(audit.MENTIONS_A_ECARTER, apply=True) == 1
    assert lire(chemin)["status"] == "discarded"
    assert audit.ecarter_mentions(audit.MENTIONS_A_ECARTER, apply=True) == 0


def test_la_simulation_n_ecrit_rien(corpus: Path):
    chemin = poser(corpus, "items", "416701f6", {
        "id": "416701f6", "title": "Salade grecque", "types": ["film"],
        "creator": "Cédric Clapichon"})
    avant = chemin.read_text(encoding="utf-8")
    audit.executer(apply=False)
    assert chemin.read_text(encoding="utf-8") == avant
