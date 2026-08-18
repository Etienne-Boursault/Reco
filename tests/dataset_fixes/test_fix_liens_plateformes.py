"""Tests de `tools/fix_liens_plateformes.py`.

Ce module pose des liens VISIBLES issus d'une recherche deleguee. Deux
proprietes comptent plus que les autres, et la moitie des tests y sont
consacres : il ne depasse JAMAIS les six liens que la carte affiche, et il
n'ecrit rien si le titre a change depuis la verification.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_liens_plateformes as flp


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


@pytest.fixture
def table(monkeypatch):
    """Table de test, substituee a celle du dépôt."""
    def poser(entrees):
        par_reco: dict[str, list[dict]] = {}
        for e in entrees:
            par_reco.setdefault(e["id"], []).append(e)
        for v in par_reco.values():
            v.sort(key=lambda e: flp.PRIORITE.get(e.get("label"), 9))
        monkeypatch.setattr(flp, "TABLE", par_reco)
    return poser


def _e(rid, label, url, titre="T"):
    return {"id": rid, "titre_attendu": titre, "label": label, "url": url,
            "kind": "streaming", "preuve": "test"}


def _lien(url):
    return {"url": url, "label": "L", "kind": "info", "ethics": "neutral"}


def test_pose_les_liens_prevus(table):
    table([_e("a", "Deezer", "https://deezer/1"), _e("a", "Bandcamp", "https://bc/1")])
    reco = {"id": "a", "title": "T", "links": []}
    changes = flp.transform(reco)
    assert [lien["url"] for lien in reco["links"]] == ["https://bc/1", "https://deezer/1"]
    assert [c.field for c in changes] == ["links"]


def test_BANDCAMP_passe_devant(table):
    """Choix editorial du depot : l'artiste y est mieux remunere. Quand il ne
    reste qu'une place, c'est lui qui la prend."""
    table([_e("a", "Spotify", "https://sp/1"), _e("a", "Bandcamp", "https://bc/1")])
    reco = {"id": "a", "title": "T", "links": [_lien(f"https://x/{i}") for i in range(5)]}
    flp.transform(reco)
    assert reco["links"][-1]["url"] == "https://bc/1"
    assert len(reco["links"]) == 6


def test_ne_depasse_JAMAIS_six_liens(table):
    """Une consigne donnee a un agent est un vœu ; ce module, lui, refuse."""
    table([_e("a", lab, f"https://x/{lab}") for lab in
           ("Bandcamp", "Deezer", "Apple Music", "Spotify", "Qobuz", "YT Music")])
    reco = {"id": "a", "title": "T", "links": [_lien("https://deja/1")]}
    flp.transform(reco)
    assert len(reco["links"]) == flp.AFFICHES


def test_une_reco_DEJA_pleine_ne_recoit_rien(table):
    table([_e("a", "Deezer", "https://deezer/1")])
    reco = {"id": "a", "title": "T", "links": [_lien(f"https://x/{i}") for i in range(6)]}
    assert flp.transform(reco) == []
    assert len(reco["links"]) == 6


def test_un_titre_QUI_A_CHANGE_annule_la_pose(table):
    """La reco peut desormais designer une autre œuvre."""
    table([_e("a", "Deezer", "https://deezer/1", titre="Ancien titre")])
    reco = {"id": "a", "title": "Nouveau titre", "links": []}
    assert flp.transform(reco) == []


def test_un_lien_DEJA_present_n_est_pas_double(table):
    table([_e("a", "Deezer", "https://deezer/1")])
    reco = {"id": "a", "title": "T", "links": [_lien("https://deezer/1")]}
    assert flp.transform(reco) == []


def test_la_passe_est_idempotente(table):
    table([_e("a", "Deezer", "https://deezer/1")])
    reco = {"id": "a", "title": "T", "links": []}
    flp.transform(reco)
    assert flp.transform(reco) == []


def test_une_reco_absente_de_la_table_n_est_pas_touchee(table):
    table([_e("a", "Deezer", "https://deezer/1")])
    reco = {"id": "zzz", "title": "T"}
    assert flp.transform(reco) == []
    assert "links" not in reco


def test_les_liens_portent_kind_streaming(table):
    table([_e("a", "Deezer", "https://deezer/1")])
    reco = {"id": "a", "title": "T", "links": []}
    flp.transform(reco)
    assert reco["links"][0]["kind"] == "streaming"
    assert reco["links"][0]["ethics"] == "neutral"


def test_charger_sur_un_fichier_absent_rend_une_table_vide(tmp_path: Path):
    assert flp.charger(tmp_path / "rien.json") == {}


def test_charger_groupe_et_trie(tmp_path: Path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps([_e("a", "Qobuz", "https://q"), _e("a", "Bandcamp", "https://b")]),
                 encoding="utf-8")
    t = flp.charger(p)
    assert [e["label"] for e in t["a"]] == ["Bandcamp", "Qobuz"]


def test_le_plafond_correspond_a_celui_de_la_carte():
    """`RecoCard` tranche a six. Si l'un des deux change sans l'autre, ce
    module ecrira des liens que personne ne verra."""
    carte = Path("src/components/RecoCard.astro").read_text(encoding="utf-8")
    assert f"slice(0, {flp.AFFICHES})" in carte


def test_main_apply_ecrit(recos_root: Path, table):
    table([_e("a", "Deezer", "https://deezer/1")])
    chemin = recos_root / "s" / "a.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps({"id": "a", "title": "T", "links": []}), encoding="utf-8")
    assert flp.main(["--apply"]) == 0
    doc = json.loads(chemin.read_text(encoding="utf-8"))
    assert doc["links"][0]["url"] == "https://deezer/1"


def test_main_dry_run_n_ecrit_pas(recos_root: Path, tmp_path: Path, table):
    table([_e("a", "Deezer", "https://deezer/1")])
    chemin = recos_root / "s" / "a.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps({"id": "a", "title": "T", "links": []}), encoding="utf-8")
    avant = chemin.read_text(encoding="utf-8")
    rapport = tmp_path / "r.json"
    assert flp.main(["--json", str(rapport)]) == 0
    assert chemin.read_text(encoding="utf-8") == avant
    assert "liens_en_table" in json.loads(rapport.read_text(encoding="utf-8"))
