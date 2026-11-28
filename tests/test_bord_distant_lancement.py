"""Tests de `bord_distant` : le plafond des lancements (M1) et « périmé » (M2), revue globale du 28/11/2026.

Aucun vrai processus ni appel réseau : `subprocess.Popen` est remplacé. Le dossier du bord est
un dossier temporaire (`RECO_BORD_DIR`).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

import bord_distant as bd

MAINTENANT = datetime(2026, 11, 28, 9, 30, tzinfo=UTC)
RESUME = {"genere": "2026-11-28T09:30:00.000Z", "sept": None, "trente": None, "jours": [],
          "signalements": {"etat": "lu", "enAttente": []}}


@pytest.fixture(autouse=True)
def bord(tmp_path, monkeypatch):
    d = tmp_path / "bord"
    monkeypatch.setenv("RECO_BORD_DIR", str(d))
    monkeypatch.setenv("RECO_AUDIENCE_KEY", "FAUSSE-CLE-DESSAI-0000")
    return d


def _ecrire_cache(bord, entree) -> None:
    bord.mkdir(parents=True, exist_ok=True)
    (bord / "distant.json").write_text(json.dumps({"audience": entree}), encoding="utf-8")


# ---- Revue globale, M1 : un rafraîchissement lancé n'est pas relancé pendant 2 min ------------
def _cache_perime(bord, minutes: int = 11) -> None:
    vieux = (MAINTENANT - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    _ecrire_cache(bord, {"etat": "ok", "detail": None, "essai": vieux, "lu": vieux,
                         "donnees": RESUME})


def test_deux_lectures_de_suite_ne_lancent_qu_un_processus(monkeypatch, bord):
    _cache_perime(bord)
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    premiere = bd.lire(maintenant=MAINTENANT)
    seconde = bd.lire(maintenant=MAINTENANT + timedelta(seconds=30))
    assert (premiere["relance"], seconde["relance"]) == (True, False)
    assert len(lances) == 1
    assert (bord / "lance-audience").read_text(encoding="utf-8") == MAINTENANT.isoformat(
        timespec="seconds")


def test_au_dela_de_2_minutes_un_nouveau_lancement_part(monkeypatch, bord):
    _cache_perime(bord)
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    bd.lire(maintenant=MAINTENANT)
    assert bd.lire(maintenant=MAINTENANT + bd.LANCEMENT_MIN)["relance"] is True
    assert len(lances) == 2


def test_un_marqueur_de_lancement_illisible_compte_comme_absent(monkeypatch, bord):
    _cache_perime(bord)
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    for abime in ("pas une date", "2026-11-28T09:29:00", "\x00", ""):  # le dernier : sans fuseau
        (bord / "lance-audience").write_text(abime, encoding="utf-8")
        assert bd.lire(maintenant=MAINTENANT)["relance"] is True
    assert len(lances) == 4


def test_un_marqueur_impossible_a_ecrire_ne_lance_rien_et_ne_remonte_pas(monkeypatch, bord,
                                                                       caplog):
    _cache_perime(bord)
    (bord / "lance-audience").mkdir()  # ni lisible ni écrivable : on ne peut pas plafonner
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    assert bd.lire(maintenant=MAINTENANT)["relance"] is False and lances == []
    assert "rafraîchissement non lancé" in caplog.text


def test_un_lancement_rate_laisse_son_marqueur_donc_ne_boucle_pas(monkeypatch, bord):
    _cache_perime(bord)

    def echoue(*_a, **_k):
        raise OSError("pas de python")
    monkeypatch.setattr(bd.subprocess, "Popen", echoue)
    assert bd.lire(maintenant=MAINTENANT)["relance"] is False
    assert (bord / "lance-audience").exists()


def test_le_marqueur_de_chaque_source_est_a_part(monkeypatch, bord):
    _cache_perime(bord)
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: None)
    bd.lire(maintenant=MAINTENANT)
    assert bd._lancer(source="github", maintenant=MAINTENANT) is True


# ---- Revue globale, M2 : une seule définition de « périmé » -----------------------------------
def test_des_donnees_ne_sont_perimees_qu_au_dela_de_2_fois_la_fraicheur():
    limite = int(2 * bd.FRAICHEUR.total_seconds())
    assert bd.donnees_perimees({"age": limite}) is False
    assert bd.donnees_perimees({"age": limite + 1}) is True
    assert bd.donnees_perimees({"age": None}) is False
    assert bd.donnees_perimees(None) is False
