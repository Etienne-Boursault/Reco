"""Tests de `tools/fix_liens_verifies.py`.

Ce module pose des liens VISIBLES, issus d'une recherche déléguée à des agents
qui n'avaient pas le droit d'écrire. Les tests portent donc autant sur ce qu'il
refuse d'écrire que sur ce qu'il écrit.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_liens_verifies as flv


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


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_ajoute_le_lien_prevu():
    reco = {"id": "ubm-0815", "title": "The Egg", "links": []}
    changes = flv.transform(reco)
    assert reco["links"][-1]["url"] == flv.LIENS["ubm-0815"][3]
    assert reco["links"][-1]["kind"] == "streaming"
    assert [c.field for c in changes] == ["links"]


def test_conserve_les_liens_existants():
    reco = {"id": "ubm-0815", "title": "The Egg",
            "links": [{"url": "https://exemple.fr/x", "label": "L"}]}
    flv.transform(reco)
    assert next(lien["url"] for lien in reco["links"]) == "https://exemple.fr/x"
    assert len(reco["links"]) == 2


def test_une_reco_sans_liste_de_liens_en_recoit_une():
    reco = {"id": "ubm-0815", "title": "The Egg"}
    flv.transform(reco)
    assert len(reco["links"]) == 1


def test_une_reco_absente_de_la_table_n_est_pas_touchee():
    reco = {"id": "ubm-9999", "title": "The Egg"}
    assert flv.transform(reco) == []
    assert "links" not in reco


def test_un_titre_QUI_A_CHANGE_annule_la_decision():
    """Le titre attendu est une garde : si le corpus a bougé depuis la
    vérification, la reco peut désigner autre chose."""
    reco = {"id": "ubm-0815", "title": "Un autre titre", "links": []}
    assert flv.transform(reco) == []
    assert reco["links"] == []


def test_la_passe_est_idempotente():
    reco = {"id": "ubm-0815", "title": "The Egg", "links": []}
    flv.transform(reco)
    assert flv.transform(reco) == []
    assert len(reco["links"]) == 1


def test_un_lien_herite_mal_forme_ne_fait_pas_lever():
    """Le corpus contient de la donnée héritée : elle ne doit pas faire tomber
    la passe."""
    reco = {"id": "ubm-0815", "title": "The Egg", "links": ["hérité", None]}
    flv.transform(reco)
    assert reco["links"][-1]["url"] == flv.LIENS["ubm-0815"][3]


# ===== Cohérence de la table ===============================================
def test_les_kind_sont_ceux_du_schema():
    """`content.config.ts` déclare une énumération fermée ; une valeur hors
    liste passe l'écriture et casse le build — c'est déjà arrivé avec
    `kind: "ticket"`."""
    admis = {"buy", "borrow", "streaming", "info", "official", "social"}
    for rid, (_, _, kind, _, _) in flv.LIENS.items():
        assert kind in admis, rid


def test_toutes_les_urls_sont_en_https():
    for rid, (_, _, _, url, _) in flv.LIENS.items():
        assert url.startswith("https://"), rid


def test_chaque_entree_porte_sa_justification():
    """Un lien sans motif n'est pas réfutable : personne ne pourra dire, plus
    tard, sur quoi la décision reposait."""
    for rid, (_, _, _, _, pourquoi) in flv.LIENS.items():
        assert len(pourquoi) > 40, rid


def test_aucune_url_en_double_sur_des_recos_differentes_sans_raison():
    """Deux recos peuvent légitimement partager un lien (deux mentions de la
    même œuvre) — mais alors leur titre attendu doit être le même."""
    par_url: dict[str, set[str]] = {}
    for _, (titre, _, _, url, _) in flv.LIENS.items():
        par_url.setdefault(url, set()).add(titre)
    for url, titres in par_url.items():
        assert len(titres) == 1, f"{url} partagé par des œuvres différentes : {titres}"


# ===== CLI =================================================================
def test_main_dry_run_n_ecrit_pas(recos_root: Path, tmp_path: Path):
    path = _write(recos_root / "s" / "a.json", {"id": "ubm-0815", "title": "The Egg"})
    avant = path.read_text(encoding="utf-8")
    report = tmp_path / "r.json"
    assert flv.main(["--json", str(report)]) == 0
    assert path.read_text(encoding="utf-8") == avant
    assert json.loads(report.read_text(encoding="utf-8"))["liens"] == len(flv.LIENS)


def test_main_apply_ecrit_le_lien(recos_root: Path):
    path = _write(recos_root / "s" / "a.json", {"id": "ubm-0815", "title": "The Egg"})
    assert flv.main(["--apply"]) == 0
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["links"][0]["url"] == flv.LIENS["ubm-0815"][3]
