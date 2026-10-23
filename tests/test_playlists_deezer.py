"""Tests pour `tools/playlists_deezer.py` — correspondance Spotify -> Deezer, sans reseau."""
from __future__ import annotations

import json

import playlists_deezer as pd


def candidat(i, titre, artiste, duree_s):
    return {"id": i, "title": titre, "artist": {"name": artiste}, "duration": duree_s}


class FauxEmbed:
    def __init__(self, infos):
        self.infos = infos

    def titre_artiste(self, tid):
        return self.infos[tid][:2]

    def duree(self, tid):
        return self.infos[tid][2]


class FauxDeezer:
    def __init__(self, isrc=None, recherche=None):
        self.isrc, self.recherche, self.cherches = isrc or {}, recherche or [], []

    def par_isrc(self, code):
        return self.isrc.get(code)

    def chercher(self, titre, artiste):
        self.cherches.append((titre, artiste))
        return self.recherche


def test_choisir_prend_la_duree_la_plus_proche():
    cands = [candidat(1, "Bliss", "Muse", 300), candidat(2, "Bliss", "Muse", 251), candidat(3, "Bliss", "Autre", 251)]
    assert pd.choisir("Bliss", "Muse", 251_000, cands) == (2, "recherche")


def test_choisir_doute_si_titre_ou_duree_s_ecartent():
    assert pd.choisir("Bliss (Live)", "Muse", 251_000, [candidat(2, "Bliss", "Muse", 251)]) == (2, "doute")
    assert pd.choisir("Bliss", "Muse", 251_000, [candidat(2, "Bliss", "Muse", 280)]) == (2, "doute")
    assert pd.choisir("Bliss", "Muse", 251_000, [candidat(3, "Hysteria", "Muse", 251)]) == (None, "absent")


def test_lire_isrc_ignore_les_inconnus():
    assert pd.lire_isrc("a=FR123 b=- c=GB9") == {"a": "FR123", "c": "GB9"}


def test_correspondance_par_isrc_d_abord():
    dz = FauxDeezer(isrc={"FR1": 42})
    assert pd.correspondance("t", "FR1", FauxEmbed({}), dz) == (42, "isrc")
    assert dz.cherches == []


def test_correspondance_cherche_aussi_le_titre_court():
    dz = FauxDeezer(recherche=[candidat(7, "Traces", "Grand Corps Malade", 200)])
    embed = FauxEmbed({"t": ("Traces (feat. SDM)", "Grand Corps Malade, SDM", 200_000)})
    assert pd.correspondance("t", None, embed, dz) == (7, "doute")
    assert dz.cherches == [("Traces (feat. SDM)", "Grand Corps Malade"), ("Traces", "Grand Corps Malade")]


def test_remplir_plan_suit_l_ordre_spotify(tmp_path, monkeypatch):
    etat = tmp_path / "playlists_deezer.json"
    etat.write_text(json.dumps({"playlists": {"Saison 6": {"id": 6, "titres": []},
                                              "Toutes les recos musicales": {"id": 9, "titres": []}}}))
    monkeypatch.setattr(pd, "ETAT", etat)
    plan = {"spotify": {"Toutes les recos musicales": {"id": "x", "ajouts": ["a", "b"]},
                        "Saison 6": {"id": "y", "ajouts": ["b", "a", "c"]}}}
    embed = FauxEmbed({"c": ("Inconnu", "Personne", 1000)})
    a_verifier = pd.remplir_plan(plan, {"a": "I1", "b": "I2"}, embed, FauxDeezer(isrc={"I1": 1, "I2": 2}))
    assert plan["deezer"] == {"Toutes les recos musicales": {"id": 9, "ajouts": [1, 2]},
                              "Saison 6": {"id": 6, "ajouts": [2, 1]}}
    assert len(a_verifier) == 1 and "absent" in a_verifier[0]
