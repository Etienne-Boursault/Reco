"""Tests de `tools/fix_ordre_liens.py`.

La carte n'affiche que six liens, et ce sont les DERNIERS qui tombent. Les
liens ajoutés par une passe d'enrichissement arrivent en fin de liste : cinq
recos d'« Une Bonne Soirée » avaient ainsi leur lien Canal+ invisible.

Ce module permute, il n'ajoute ni ne retire rien — c'est ce que vérifient la
moitié des tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_ordre_liens as fol


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


def _lien(url, kind):
    return {"url": url, "label": url, "kind": kind, "ethics": "neutral"}


def _sept(dernier_kind="streaming"):
    return [_lien(f"https://x/{i}", "official") for i in range(6)] + [
        _lien("https://x/utile", dernier_kind)]


def test_remonte_le_lien_d_acces_au_dessus_de_la_coupe():
    reco = {"id": "a", "links": _sept()}
    changes = fol.transform(reco)
    assert reco["links"][0]["url"] == "https://x/utile"
    assert [c.field for c in changes] == ["links"]


def test_ne_touche_pas_une_reco_de_six_liens_ou_moins():
    """En deçà de la coupe, l'ordre du corpus est intentionnel."""
    liens = [_lien("https://x/social", "social"), _lien("https://x/voir", "streaming")]
    reco = {"id": "a", "links": list(liens)}
    assert fol.transform(reco) == []
    assert [lien["url"] for lien in reco["links"]] == [lien["url"] for lien in liens]


def test_ne_perd_ni_n_ajoute_aucun_lien():
    reco = {"id": "a", "links": _sept()}
    avant = {lien["url"] for lien in reco["links"]}
    fol.transform(reco)
    assert {lien["url"] for lien in reco["links"]} == avant
    assert len(reco["links"]) == 7


def test_conserve_l_ordre_cure_a_priorite_egale():
    """Le tri est stable : deux liens de même `kind` ne permutent pas."""
    reco = {"id": "a", "links": [_lien(f"https://x/{i}", "info") for i in range(7)]}
    assert fol.transform(reco) == []


def test_un_kind_inconnu_se_range_au_milieu():
    reco = {"id": "a", "links": [_lien("https://x/bizarre", "zzz")]
            + [_lien(f"https://x/{i}", "social") for i in range(6)]}
    fol.transform(reco)
    assert reco["links"][0]["url"] == "https://x/bizarre"


def test_la_passe_est_idempotente():
    reco = {"id": "a", "links": _sept()}
    fol.transform(reco)
    assert fol.transform(reco) == []


def test_une_liste_contenant_de_l_HERITE_est_laissee_intacte():
    """Mélanger des entrées non conformes ferait perdre celles qu'on ne sait
    pas trier : on préfère ne rien faire."""
    reco = {"id": "a", "links": _sept() + ["hérité"]}
    assert fol.transform(reco) == []


def test_une_reco_sans_liens_ne_leve_pas():
    assert fol.transform({"id": "a"}) == []


def test_la_coupe_correspond_a_celle_de_la_carte():
    """`RecoCard` tranche à six (`slice(0, 6)`). Si l'un des deux change sans
    l'autre, ce module réordonne pour rien — ou pas assez."""
    carte = Path("src/components/RecoCard.astro").read_text(encoding="utf-8")
    assert f"slice(0, {fol.AFFICHES})" in carte


def test_main_apply_ecrit(recos_root: Path):
    chemin = recos_root / "s" / "a.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps({"id": "a", "links": _sept()}, ensure_ascii=False),
                      encoding="utf-8")
    assert fol.main(["--apply"]) == 0
    doc = json.loads(chemin.read_text(encoding="utf-8"))
    assert doc["links"][0]["url"] == "https://x/utile"


def test_main_dry_run_n_ecrit_pas(recos_root: Path, tmp_path: Path):
    chemin = recos_root / "s" / "a.json"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps({"id": "a", "links": _sept()}, ensure_ascii=False),
                      encoding="utf-8")
    avant = chemin.read_text(encoding="utf-8")
    rapport = tmp_path / "r.json"
    assert fol.main(["--json", str(rapport)]) == 0
    assert chemin.read_text(encoding="utf-8") == avant
    assert json.loads(rapport.read_text(encoding="utf-8"))["affiches"] == fol.AFFICHES
