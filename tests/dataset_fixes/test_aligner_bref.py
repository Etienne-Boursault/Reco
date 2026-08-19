"""Tests de `tools/aligner_bref.py`.

CE QUE LA RELECTURE A VU
------------------------
Une capture de la page `/recos` filtree sur « Bref » : seize cartes de la meme
serie, avec cinq graphies de createur — « Kyan Khojandi », « Kyan Khojandi,
Bruno Muschio », « Kyan Khojandi, Navo », « Kyan Khojandi, Alain Chabat », et
une sans createur du tout — et des jeux de liens allant de trois a six.

Demande : « aligne les recos Bref pour qu'elles aient bien le meme createur
Kyan et Navo et aussi les memes liens ».

CE QUI EST RETENU
-----------------
Le createur : « Kyan Khojandi, Navo ». Navo est le nom de scene de Bruno
Muschio — les deux graphies designent la meme personne, et c'est celle que
l'editeur a choisie. Alain Chabat a PRODUIT la serie sans la creer : il sort.

Les liens : ceux de la reco la plus complete, verifies un par un. Six pour
« Bref », ce qui est exactement le plafond d'affichage de la carte.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import aligner_bref as ab


@pytest.fixture
def recos_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "recos"
    root.mkdir()
    monkeypatch.setattr(common, "RECOS_DIR", root)
    monkeypatch.setattr(df, "RECOS_DIR", root)
    items = tmp_path / "items"
    items.mkdir()
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(df, "ITEMS_DIR", items)
    return root


# ===== Le createur =========================================================
@pytest.mark.parametrize("avant", [
    "Kyan Khojandi",
    "Kyan Khojandi, Bruno Muschio",
    "Kyan Khojandi, Alain Chabat",
    None,
])
def test_toutes_les_graphies_convergent(avant):
    reco = {"id": "x", "title": "Bref", "creator": avant, "types": ["serie"]}
    ab.transform(reco)
    assert reco["creator"] == "Kyan Khojandi, Navo"


def test_une_reco_deja_alignee_n_est_pas_reecrite():
    reco = {"id": "x", "title": "Bref", "creator": "Kyan Khojandi, Navo",
            "types": ["serie"], "links": [dict(lien) for lien in ab.LIENS["bref"]]}
    assert ab.transform(reco) == []


# ===== Les liens ===========================================================
def test_les_liens_sont_REMPLACES_par_la_reference():
    reco = {"id": "x", "title": "Bref", "types": ["serie"],
            "links": [{"url": "https://exemple.fr/x", "label": "L", "kind": "info"}]}
    ab.transform(reco)
    assert [lien["url"] for lien in reco["links"]] == [
        lien["url"] for lien in ab.LIENS["bref"]]


def test_bref_tient_dans_le_plafond_de_la_carte():
    """`RecoCard` n'affiche que six liens : un septieme serait invisible."""
    for titre, liens in ab.LIENS.items():
        assert len(liens) <= 6, titre


def test_bref_2_a_ses_PROPRES_liens():
    """C'est une autre oeuvre — la saison 2 — avec sa propre page Disney+."""
    reco = {"id": "x", "title": "Bref 2", "types": ["serie"]}
    ab.transform(reco)
    urls = [lien["url"] for lien in reco["links"]]
    assert urls == [lien["url"] for lien in ab.LIENS["bref 2"]]
    assert urls != [lien["url"] for lien in ab.LIENS["bref"]]


# ===== Les gardes ==========================================================
def test_un_titre_hors_perimetre_n_est_pas_touche():
    reco = {"id": "x", "title": "Bref. De bons amis", "creator": "Nicolas Béguet"}
    assert ab.transform(reco) == []
    assert reco["creator"] == "Nicolas Béguet"


def test_une_reco_ECARTEE_n_est_pas_touchee():
    """Elle ne s'affiche nulle part : l'aligner ne servirait a rien et
    brouillerait la trace de ce qui a ete ecarte."""
    reco = {"id": "x", "title": "Bref", "status": "discarded"}
    assert ab.transform(reco) == []


def test_le_titre_est_compare_sans_la_casse():
    reco = {"id": "x", "title": "BREF", "types": ["serie"]}
    assert ab.transform(reco) != []


def test_la_passe_est_idempotente():
    reco = {"id": "x", "title": "Bref", "types": ["serie"]}
    ab.transform(reco)
    assert ab.transform(reco) == []


# ===== Coherence de la table ==============================================
def test_les_kind_sont_ceux_du_schema():
    admis = {"buy", "borrow", "streaming", "info", "official", "social"}
    for titre, liens in ab.LIENS.items():
        for lien in liens:
            assert lien["kind"] in admis, (titre, lien)


def test_toutes_les_urls_sont_en_https():
    for titre, liens in ab.LIENS.items():
        for lien in liens:
            assert lien["url"].startswith("https://"), (titre, lien)


def test_aucun_lien_en_double_dans_une_meme_liste():
    for titre, liens in ab.LIENS.items():
        urls = [lien["url"] for lien in liens]
        assert len(urls) == len(set(urls)), titre


# ===== CLI =================================================================
def test_main_apply(recos_root: Path):
    p = recos_root / "a.json"
    p.write_text(json.dumps({"id": "a", "title": "Bref", "types": ["serie"],
                             "creator": "Kyan Khojandi"}), encoding="utf-8")
    assert ab.main(["--apply"]) == 0
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["creator"] == "Kyan Khojandi, Navo"
    assert len(doc["links"]) == 6


def test_main_dry_run_n_ecrit_pas(recos_root: Path):
    p = recos_root / "a.json"
    p.write_text(json.dumps({"id": "a", "title": "Bref", "types": ["serie"]}),
                 encoding="utf-8")
    avant = p.read_text(encoding="utf-8")
    assert ab.main([]) == 0
    assert p.read_text(encoding="utf-8") == avant
