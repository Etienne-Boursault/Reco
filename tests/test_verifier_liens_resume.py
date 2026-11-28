"""Tests du résumé que `verifier_liens.py` écrit pour le tableau de bord (tranche 3c).

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026. Le résumé vit sous
`RECO_BORD_DIR` (un dossier temporaire ici) : aucun test n'écrit dans `tools/output/`.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

import bord_contenu
import verifier_liens as vl
from link_check import ProbeResult


@pytest.fixture(autouse=True)
def bord(tmp_path, monkeypatch):
    monkeypatch.setenv("RECO_BORD_DIR", str(tmp_path / "bord"))
    return tmp_path / "bord"


def _rapport(morts, nouveaux=(), inconnus=None, vivants=0):
    return vl.Rapport("2026-11-23", morts={u: {"reponse": "HTTP 404", "recos": [], "pages": []}
                                           for u in morts},
                      inconnus_par_site=inconnus or {}, vivants=vivants, nouveaux=list(nouveaux))


def test_le_resume_donne_les_comptes_et_la_date(bord):
    rapport = _rapport(["https://m.example/1"], nouveaux=["https://m.example/1"],
                       inconnus={"netflix.com": 3, "deezer.com": 2}, vivants=40)
    vl.ecrire_resume(rapport)
    resume = json.loads((bord / "liens.json").read_text(encoding="utf-8"))
    assert resume["date"] == "2026-11-23"
    assert (resume["morts"], resume["nouveaux"], resume["inconnus"], resume["vivants"]) == (
        1, 1, 5, 40)
    assert resume["liste"] == [{"url": "https://m.example/1", "reponse": "HTTP 404", "recos": []}]


def test_la_liste_met_les_nouveaux_d_abord_puis_l_ordre_des_adresses_et_dit_le_total(bord):
    morts = [f"https://m.example/{k:02d}" for k in range(15)]
    vl.ecrire_resume(_rapport(morts, nouveaux=[morts[14], morts[13]]))
    resume = json.loads((bord / "liens.json").read_text(encoding="utf-8"))
    assert resume["morts"] == 15 and len(resume["liste"]) == vl.RESUME_MAX
    assert [m["url"] for m in resume["liste"][:4]] == [
        morts[13], morts[14], morts[0], morts[1]]


def test_le_resume_garde_les_recos_et_se_relit_par_le_tableau_de_bord(bord):
    rapport = vl.rapporter({"https://m.example/": ProbeResult("dead", "HTTP 410")}, {},
                           {"https://m.example/": ["r2", "r1", "r1"]}, set())
    rapport.date = datetime.now(UTC).strftime("%Y-%m-%d")
    vl.ecrire_resume(rapport)
    liens = bord_contenu._liens(datetime.now(UTC))
    assert liens["morts"] == 1 and liens["ancien"] is False
    assert liens["liste"][0]["recos"] == ["r1", "r2"]


def test_une_ecriture_refusee_ne_fait_pas_tomber_le_rapport(bord, tmp_path):
    bord.parent.mkdir(parents=True, exist_ok=True)
    bord.write_text("je suis un fichier, pas un dossier", encoding="utf-8")
    vl.ecrire_resume(_rapport([]))  # ne lève pas
    assert bord.read_text(encoding="utf-8").startswith("je suis")


def test_externes_ecrit_le_resume_a_cote_du_rapport(bord, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<a href="https://m.example/x">m</a>', encoding="utf-8")
    recos = tmp_path / "recos"
    recos.mkdir()
    monkeypatch.setattr(vl, "sonder", lambda urls: {u: ProbeResult("dead", "HTTP 404") for u in urls})
    assert vl.main(["externes", str(dist), "--recos", str(recos), "--etat",
                    str(tmp_path / "etat.json"), "--sortie", str(tmp_path / "rapports")]) == 0
    resume = json.loads((bord / "liens.json").read_text(encoding="utf-8"))
    assert resume["morts"] == 1 and resume["nouveaux"] == 1
    assert not list(bord.glob("*.tmp"))
