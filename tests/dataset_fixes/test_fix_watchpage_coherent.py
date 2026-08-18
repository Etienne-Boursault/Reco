"""Tests de `tools/fix_watchpage_coherent.py`.

L'INVARIANT
-----------
`externalIds.watchPage` est l'adresse « où regarder » d'une oeuvre sur TMDB.
Elle se DEDUIT de `externalIds.tmdb` : meme identifiant, meme page. Ce n'est
pas une donnee independante, c'est un derive.

Cinq recos violaient pourtant cet invariant le 2026-08-18, et chacune envoyait
le visiteur sur une AUTRE oeuvre :

    « Vice » (Adam McKay, 2018)   -> « Vice-versa » (Pixar, 2015)   x2
    « Fantomas » (de Funes, 1964) -> « Fantomas », le muet de 1913
    « Looking » (2014)            -> « Looking up to Magical Girls » (2024)
    « Bagarre »                   -> « Picture Snatcher » (1933)

Dans les cinq cas, l'identifiant machine etait JUSTE et c'est l'adresse qui
mentait. Le bouton disait « Où regarder » et menait ailleurs.

POURQUOI UNE REGLE, ET NON UNE TABLE DE CINQ ENTREES
-----------------------------------------------------
Une table curee ne corrigerait que ces cinq-la. La regle, elle, vaut pour tout
le corpus et pour ce qui s'y ajoutera : une adresse derivee ne peut pas
diverger de ce dont elle derive. Un cas sur les cinq — la reco « Bagarre » —
avait d'ailleurs echappe au correctif cure de la veille, qui ne visait que
l'item correspondant.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_watchpage_coherent as fwc


@pytest.fixture
def racines(tmp_path: Path, monkeypatch):
    recos = tmp_path / "recos"
    items = tmp_path / "items"
    recos.mkdir()
    items.mkdir()
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    monkeypatch.setattr(df, "RECOS_DIR", recos)
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(df, "ITEMS_DIR", items)
    return recos, items


# ===== Le desaccord ========================================================
def test_une_adresse_qui_designe_une_AUTRE_oeuvre_est_refaite():
    """« Vice » d'Adam McKay pointait vers « Vice-versa » de Pixar."""
    doc = {"id": "ubm-0797", "title": "Vice",
           "externalIds": {
               "tmdb": "429197", "tmdbType": "movie",
               "watchPage": "https://www.themoviedb.org/movie/"
                            "150540-vice-versa/watch?locale=FR"}}
    changes = fwc.transform(doc)
    assert doc["externalIds"]["watchPage"] == (
        "https://www.themoviedb.org/movie/429197/watch?locale=FR")
    assert [c.field for c in changes] == ["externalIds.watchPage"]


def test_le_TYPE_aussi_doit_concorder():
    """Un `movie/` la ou l'identifiant est une serie mene a une page vide."""
    doc = {"id": "x", "title": "T",
           "externalIds": {
               "tmdb": 57774, "tmdbType": "tv",
               "watchPage": "https://www.themoviedb.org/movie/57774/watch?locale=FR"}}
    fwc.transform(doc)
    assert doc["externalIds"]["watchPage"] == (
        "https://www.themoviedb.org/tv/57774/watch?locale=FR")


def test_une_adresse_ORPHELINE_est_supprimee():
    """Sans identifiant, l'adresse ne derive plus de rien. C'est le cas de la
    reco « Bagarre », que le correctif cure de la veille avait manquee : il ne
    visait que l'item, pas la reco."""
    doc = {"id": "ubm-1363", "title": "Bagarre",
           "externalIds": {"watchPage": "https://www.themoviedb.org/movie/"
                                        "49064-picture-snatcher/watch?locale=FR"}}
    fwc.transform(doc)
    assert "watchPage" not in (doc.get("externalIds") or {})


def test_un_externalIds_vide_apres_coup_disparait():
    doc = {"id": "x", "title": "T",
           "externalIds": {"watchPage": "https://www.themoviedb.org/movie/1/watch"}}
    fwc.transform(doc)
    assert "externalIds" not in doc


# ===== Ce qu'on ne touche pas ==============================================
def test_une_adresse_DEJA_coherente_n_est_pas_reecrite():
    """Y compris avec un slug : TMDB l'ignore, et la reecrire pour la seule
    forme produirait un diff de 269 fichiers sans rien corriger."""
    doc = {"id": "x", "title": "T",
           "externalIds": {
               "tmdb": 94801, "tmdbType": "tv",
               "watchPage": "https://www.themoviedb.org/tv/"
                            "94801-mortel/watch?locale=FR"}}
    assert fwc.transform(doc) == []
    assert "mortel" in doc["externalIds"]["watchPage"]


def test_un_document_sans_watchPage_n_est_pas_touche():
    doc = {"id": "x", "title": "T", "externalIds": {"tmdb": 42, "tmdbType": "movie"}}
    assert fwc.transform(doc) == []
    assert "watchPage" not in doc["externalIds"]


def test_un_document_sans_externalIds_ne_fait_pas_lever():
    assert fwc.transform({"id": "x", "title": "T"}) == []


def test_un_externalIds_mal_forme_ne_fait_pas_lever():
    for mauvais in ("texte", [], 42, None):
        assert fwc.transform({"id": "x", "externalIds": mauvais}) == [], mauvais


def test_une_adresse_HORS_TMDB_est_laissee_telle_quelle():
    """Le champ pourrait porter autre chose ; on ne prend pas la main sur ce
    qu'on ne sait pas lire."""
    doc = {"id": "x", "title": "T",
           "externalIds": {"tmdb": 42, "tmdbType": "movie",
                           "watchPage": "https://www.justwatch.com/fr/film/x"}}
    assert fwc.transform(doc) == []


def test_la_passe_est_idempotente():
    doc = {"id": "x", "title": "T",
           "externalIds": {
               "tmdb": 1, "tmdbType": "movie",
               "watchPage": "https://www.themoviedb.org/movie/999/watch?locale=FR"}}
    fwc.transform(doc)
    assert fwc.transform(doc) == []


# ===== CLI =================================================================
def test_main_traite_recos_ET_items(racines):
    recos, items = racines
    faux = {"tmdb": 429197, "tmdbType": "movie",
            "watchPage": "https://www.themoviedb.org/movie/150540/watch?locale=FR"}
    (recos / "a.json").write_text(json.dumps(
        {"id": "a", "title": "Vice", "externalIds": dict(faux)}), encoding="utf-8")
    (items / "b.json").write_text(json.dumps(
        {"id": "b", "title": "Vice", "externalIds": dict(faux)}), encoding="utf-8")
    assert fwc.main(["--apply"]) == 0
    for chemin in (recos / "a.json", items / "b.json"):
        doc = json.loads(chemin.read_text(encoding="utf-8"))
        assert "429197" in doc["externalIds"]["watchPage"]


def test_main_dry_run_n_ecrit_pas(racines):
    recos, _ = racines
    p = recos / "a.json"
    p.write_text(json.dumps(
        {"id": "a", "title": "Vice",
         "externalIds": {"tmdb": 429197, "tmdbType": "movie",
                         "watchPage": "https://www.themoviedb.org/movie/"
                                      "150540/watch?locale=FR"}}), encoding="utf-8")
    avant = p.read_text(encoding="utf-8")
    assert fwc.main([]) == 0
    assert p.read_text(encoding="utf-8") == avant


def test_un_identifiant_SANS_type_rend_l_adresse_orpheline():
    """L'adresse a besoin des DEUX : sans `tmdbType`, impossible de savoir
    s'il faut ecrire `/movie/` ou `/tv/`, et se tromper mene a une page vide.
    Mieux vaut pas d'adresse qu'une adresse devinee."""
    doc = {"id": "x", "title": "T",
           "externalIds": {"tmdb": 42,
                           "watchPage": "https://www.themoviedb.org/movie/"
                                        "42/watch?locale=FR"}}
    fwc.transform(doc)
    assert "watchPage" not in (doc.get("externalIds") or {})
    assert doc["externalIds"]["tmdb"] == 42, "l'identifiant, lui, reste"
