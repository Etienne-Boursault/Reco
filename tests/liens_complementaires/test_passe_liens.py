"""Tests de la boucle commune : sélection, écriture, placement, audit trail.

Le disque est réel (`tmp_path`), la résolution est un double : c'est
l'enchaînement qu'on éprouve ici, pas un site.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import passe_liens as pl
from _liens_fakes import ecrire_reco, lire
from enrichment.field_refresher import EnrichedAtCorruptedError
from wikidata_matching import Lien, Resolution

NETFLIX = Lien("netflix", "streaming", "neutral", "Netflix",
               "https://www.netflix.com/title/81447461")
IMDB = {"ethics": "neutral", "kind": "info", "label": "IMDb",
        "url": "https://www.imdb.com/title/tt14403178/"}


@pytest.fixture()
def racine(tmp_path: Path) -> Path:
    r = tmp_path / "recos"
    ecrire_reco(r, "src", {"id": "s-1", "title": "Acharnés", "types": ["serie"],
                           "status": "validated", "links": [IMDB]})
    ecrire_reco(r, "src", {"id": "s-2", "title": "Brouillon", "types": ["serie"],
                           "status": "draft", "links": []})
    ecrire_reco(r, "src", {"id": "s-3", "title": "Un livre", "types": ["livre"],
                           "status": "validated", "links": []})
    return r


def _servie(reco):
    return "serie" in reco.get("types", [])


def _toujours(liens):
    return lambda reco: Resolution(tuple(liens), "ok", "preuve")


# ===== appliquer ============================================================
def test_appliquer_place_le_lien_et_trace_lecriture():
    reco = {"links": [IMDB]}

    pl.appliquer(reco, [NETFLIX], placer=lambda _l, _n: 0, timestamp="2026-10-10T00:00:00Z")

    assert [lien["label"] for lien in reco["links"]] == ["Netflix", "IMDb"]
    assert reco["enrichedAt"]["links"] == "2026-10-10T00:00:00Z"


def test_appliquer_ne_repose_jamais_un_hote_present():
    """Un lien posé à la main n'est jamais doublé, ni remplacé."""
    reco = {"links": [{"url": "https://www.netflix.com/title/1"}]}

    pl.appliquer(reco, [NETFLIX, NETFLIX])

    assert reco["links"] == [{"url": "https://www.netflix.com/title/1"}]
    assert "enrichedAt" not in reco


def test_appliquer_ajoute_a_la_fin_par_defaut_et_sans_doublon_dans_le_lot():
    reco = {"links": [IMDB]}
    autre = Lien("netflix", "streaming", "neutral", "Netflix", "https://netflix.com/title/2")

    pl.appliquer(reco, [NETFLIX, autre])

    assert [lien["url"] for lien in reco["links"]] == [IMDB["url"], NETFLIX.url]


# ===== derouler =============================================================
def test_seules_les_recos_servies_et_voulues_sont_vues(racine):
    rapport = pl.derouler(root=racine, source="src", ids={"s-1", "s-2"}, servie=_servie,
                          resoudre=_toujours([]), apply=False)

    assert rapport.vues == 2
    assert [(c.reco_id, c.raison) for c in rapport.cas] == [("s-1", "ok"),
                                                            ("s-2", "not-validated")]


def test_apply_ecrit_et_compte(racine):
    rapport = pl.derouler(root=racine, source="src", ids=(), servie=_servie,
                          resoudre=_toujours([NETFLIX]), apply=True,
                          placer=lambda _l, _n: 0)

    assert rapport.ecrites == 1 and rapport.servies == {"s-1"}
    assert lire(racine / "src" / "s-1.json")["links"][0]["label"] == "Netflix"


def test_un_lien_deja_present_ne_reecrit_pas_le_fichier(racine):
    deja = Lien("imdb", "info", "neutral", "IMDb", IMDB["url"])

    rapport = pl.derouler(root=racine, source="src", ids=(), servie=_servie,
                          resoudre=_toujours([deja]), apply=True)

    assert rapport.ecrites == 0


def test_sans_apply_rien_nest_ecrit(racine):
    avant = (racine / "src" / "s-1.json").read_text(encoding="utf-8")

    rapport = pl.derouler(root=racine, source="src", ids=(), servie=_servie,
                          resoudre=_toujours([NETFLIX]), apply=False)

    assert rapport.ecrites == 0 and rapport.liens_poses == 1
    assert (racine / "src" / "s-1.json").read_text(encoding="utf-8") == avant


def test_un_fichier_illisible_est_signale_sans_arreter_la_passe(racine):
    (racine / "src" / "s-0.json").write_text("{pas du json", encoding="utf-8")

    rapport = pl.derouler(root=racine, source="src", ids=(), servie=_servie,
                          resoudre=_toujours([]), apply=False)

    assert ("s-0", "unreadable") in [(c.reco_id, c.raison) for c in rapport.cas]
    assert rapport.vues == 2


def test_un_audit_trail_corrompu_nest_pas_ecrit(racine, monkeypatch):
    def casse(*_a, **_k):
        raise EnrichedAtCorruptedError("enrichedAt n'est pas un objet")

    monkeypatch.setattr(pl, "appliquer", casse)

    rapport = pl.derouler(root=racine, source="src", ids=(), servie=_servie,
                          resoudre=_toujours([NETFLIX]), apply=True)

    assert rapport.ecrites == 0
    assert lire(racine / "src" / "s-1.json")["links"] == [IMDB]


def test_la_pause_est_observee_entre_deux_recos(racine, monkeypatch):
    pauses = []
    monkeypatch.setattr(pl.time, "sleep", pauses.append)

    pl.derouler(root=racine, source="src", ids=(), servie=_servie,
                resoudre=_toujours([]), apply=False, sleep=0.3)

    assert pauses == [0.3]
