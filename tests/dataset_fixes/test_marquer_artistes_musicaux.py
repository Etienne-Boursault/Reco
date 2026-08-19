"""Tests de `tools/marquer_artistes_musicaux.py`.

LE PROBLEME
-----------
La page `/musique` retient les types `musique`, `album` et `artiste`. Or
`artiste` est generique : Albert Dupontel et Hakim Jemili le portent, et se
retrouvaient donc dans la galerie musicale. Signale a la relecture du
2026-08-19.

Sur les 358 artistes du corpus, 303 n'ont QUE ce type — rien ne dit s'ils
font de la musique.

LE SIGNAL
---------
Il est dans les RECOS. Une reco de type `artiste` qui porte un lien Deezer,
Spotify, Bandcamp, Qobuz, Apple Music ou YouTube Music designe un musicien :
personne ne pose un lien d'ecoute sur un acteur. 79 titres sur 173 sont dans
ce cas.

LA CONVENTION EXISTE DEJA
-------------------------
28 items portent `['artiste', 'musique']`. On ne cree donc aucun type : on
propage une convention deja en place, que la page `/musique` pourra utiliser
comme critere.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import marquer_artistes_musicaux as mam


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch):
    recos = tmp_path / "recos"
    items = tmp_path / "items"
    recos.mkdir()
    items.mkdir()
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    return recos, items


def _reco(chemin: Path, titre: str, urls: list[str], types=("artiste",), statut="validated"):
    chemin.write_text(json.dumps({
        "id": "ubm-0001", "title": titre, "status": statut, "types": list(types),
        "links": [{"url": u, "label": "L"} for u in urls],
    }, ensure_ascii=False), encoding="utf-8")


def _item(chemin: Path, titre: str, types=("artiste",)):
    chemin.write_text(json.dumps({
        "id": "aaa", "title": titre, "types": list(types),
    }, ensure_ascii=False), encoding="utf-8")


# ===== Le marquage =========================================================
def test_un_artiste_avec_lien_d_ecoute_recoit_le_type_musique(corpus):
    recos, items = corpus
    _reco(recos / "a.json", "Orelsan", ["https://www.deezer.com/artist/12"])
    _item(items / "b.json", "Orelsan")
    mam.executer(apply=True)
    doc = json.loads((items / "b.json").read_text(encoding="utf-8"))
    assert doc["types"] == ["artiste", "musique"]


@pytest.mark.parametrize("url", [
    "https://open.spotify.com/artist/x",
    "https://music.apple.com/fr/artist/x",
    "https://www.qobuz.com/artist/x",
    "https://x.bandcamp.com/",
    "https://music.youtube.com/channel/x",
])
def test_toutes_les_plateformes_d_ecoute_comptent(corpus, url):
    recos, items = corpus
    _reco(recos / "a.json", "Untel", [url])
    _item(items / "b.json", "Untel")
    mam.executer(apply=True)
    assert "musique" in json.loads((items / "b.json").read_text(encoding="utf-8"))["types"]


# ===== Ce qu'il refuse de faire ============================================
def test_un_artiste_SANS_lien_d_ecoute_reste_intact(corpus):
    """Albert Dupontel est un artiste, pas un musicien."""
    recos, items = corpus
    _reco(recos / "a.json", "Albert Dupontel", ["https://www.imdb.com/name/x"])
    _item(items / "b.json", "Albert Dupontel")
    mam.executer(apply=True)
    assert json.loads((items / "b.json").read_text(encoding="utf-8"))["types"] == ["artiste"]


def test_un_item_qui_n_est_pas_artiste_est_ignore(corpus):
    recos, items = corpus
    _reco(recos / "a.json", "Un film", ["https://www.deezer.com/album/1"], types=("film",))
    _item(items / "b.json", "Un film", types=("film",))
    mam.executer(apply=True)
    assert json.loads((items / "b.json").read_text(encoding="utf-8"))["types"] == ["film"]


def test_une_reco_ECARTEE_ne_prouve_rien(corpus):
    """Elle a ete jugee hors sujet : s'y fier reviendrait a marquer sur une
    donnee que l'editeur a explicitement retiree."""
    recos, items = corpus
    _reco(recos / "a.json", "Untel", ["https://www.deezer.com/artist/1"], statut="discarded")
    _item(items / "b.json", "Untel")
    mam.executer(apply=True)
    assert json.loads((items / "b.json").read_text(encoding="utf-8"))["types"] == ["artiste"]


def test_un_artiste_deja_marque_n_est_pas_touche(corpus):
    recos, items = corpus
    _reco(recos / "a.json", "Untel", ["https://www.deezer.com/artist/1"])
    _item(items / "b.json", "Untel", types=("artiste", "musique"))
    rapport = mam.executer(apply=True)
    assert rapport["marques"] == 0


def test_le_titre_est_compare_sans_la_casse(corpus):
    recos, items = corpus
    _reco(recos / "a.json", "ORELSAN", ["https://www.deezer.com/artist/1"])
    _item(items / "b.json", "Orelsan")
    assert mam.executer(apply=True)["marques"] == 1


def test_rien_n_est_ecrit_sans_apply(corpus):
    recos, items = corpus
    _reco(recos / "a.json", "Untel", ["https://www.deezer.com/artist/1"])
    _item(items / "b.json", "Untel")
    avant = (items / "b.json").read_text(encoding="utf-8")
    rapport = mam.executer(apply=False)
    assert (items / "b.json").read_text(encoding="utf-8") == avant
    assert rapport["marques"] == 1


def test_un_json_illisible_ne_fait_pas_tomber_la_passe(corpus):
    recos, items = corpus
    (recos / "casse.json").write_text("{ pas du json", encoding="utf-8")
    (items / "casse.json").write_text("}{", encoding="utf-8")
    _reco(recos / "a.json", "Untel", ["https://www.deezer.com/artist/1"])
    _item(items / "b.json", "Untel")
    assert mam.executer(apply=True)["marques"] == 1


# ===== CLI =================================================================
def test_main_dry_run_par_defaut(corpus):
    recos, items = corpus
    _reco(recos / "a.json", "Untel", ["https://www.deezer.com/artist/1"])
    _item(items / "b.json", "Untel")
    avant = (items / "b.json").read_text(encoding="utf-8")
    assert mam.main([]) == 0
    assert (items / "b.json").read_text(encoding="utf-8") == avant


def test_main_apply(corpus):
    recos, items = corpus
    _reco(recos / "a.json", "Untel", ["https://www.deezer.com/artist/1"])
    _item(items / "b.json", "Untel")
    assert mam.main(["--apply"]) == 0
    assert "musique" in json.loads((items / "b.json").read_text(encoding="utf-8"))["types"]
