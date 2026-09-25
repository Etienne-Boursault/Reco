"""Tests du périmètre et de la simulation de `enrich_tmdb` (`run`, `--ids`, `--dry-run`).

La chaîne de venus appelle cette passe sur les seules recos de l'épisode qu'elle
finalise : sans périmètre, elle retraiterait les 3 000 recos du corpus, soit
autant d'appels d'API et d'écritures. Et l'outil écrivait sans filet, là où
l'enrichisseur musical simule par défaut.

Aucun appel réseau : `responses` intercepte tout.
"""
from __future__ import annotations

import json
import sys

import pytest
import requests
import responses

import enrich_tmdb
from common import parse_ids_option


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    dossier = tmp_path / "recos" / "src"
    dossier.mkdir(parents=True)
    monkeypatch.setattr(enrich_tmdb, "recos_dir_for", lambda _s: dossier)
    monkeypatch.setattr(enrich_tmdb.time, "sleep", lambda *_: None)
    monkeypatch.setattr(enrich_tmdb, "load_dotenv", lambda *a, **k: None)
    return dossier


def _reco(dossier, reco_id, **champs):
    donnees = {"id": reco_id, "title": f"Titre {reco_id}", "types": ["film"], **champs}
    chemin = dossier / f"{reco_id}.json"
    chemin.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    return chemin


def _tmdb_repond(tmdb_id: int = 42, providers: bool = True):
    responses.add(responses.GET, "https://api.themoviedb.org/3/search/movie",
                  json={"results": [{"id": tmdb_id}]}, status=200)
    responses.add(responses.GET, "https://api.themoviedb.org/3/search/tv",
                  json={"results": [{"id": tmdb_id}]}, status=200)
    fr = {"link": "https://www.themoviedb.org/movie/42/watch?locale=FR"}
    if providers:
        fr["flatrate"] = [{"provider_name": "Netflix"}]
    responses.add(responses.GET, f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers",
                  json={"results": {"FR": fr}}, status=200)
    responses.add(responses.GET, f"https://api.themoviedb.org/3/tv/{tmdb_id}/watch/providers",
                  json={"results": {"FR": fr}}, status=200)


# ===== périmètre =============================================================
@responses.activate
def test_run_only_touches_the_requested_ids(corpus):
    """Le cœur du besoin : une reco hors périmètre ne doit pas bouger d'un octet."""
    _tmdb_repond()
    voulue = _reco(corpus, "a")
    autre = _reco(corpus, "b")
    avant = autre.read_text(encoding="utf-8")

    rapport = enrich_tmdb.run(source="src", api_key="fake", ids={"a"})

    assert rapport.servies == {"a"}
    assert rapport.vues == 1 and rapport.ecrites == 1
    assert json.loads(voulue.read_text(encoding="utf-8"))["externalIds"]["tmdb"] == "42"
    assert autre.read_text(encoding="utf-8") == avant


@responses.activate
def test_run_without_ids_keeps_taking_the_whole_source(corpus):
    """Comportement historique préservé : sans `ids`, tout le corpus est vu."""
    _tmdb_repond()
    _reco(corpus, "a")
    _reco(corpus, "b")

    assert enrich_tmdb.run(source="src", api_key="fake").servies == {"a", "b"}


@responses.activate
def test_run_ignores_types_it_does_not_serve(corpus):
    """Un livre ou un jeu n'a rien à faire sur TMDB, même demandé explicitement."""
    _tmdb_repond()
    livre = _reco(corpus, "a", types=["livre"])
    avant = livre.read_text(encoding="utf-8")

    rapport = enrich_tmdb.run(source="src", api_key="fake", ids={"a"})

    assert rapport.vues == 0 and rapport.cas == []
    assert livre.read_text(encoding="utf-8") == avant


@responses.activate
def test_run_reports_a_title_tmdb_does_not_know(corpus):
    responses.add(responses.GET, "https://api.themoviedb.org/3/search/movie",
                  json={"results": []}, status=200)
    responses.add(responses.GET, "https://api.themoviedb.org/3/search/tv",
                  json={"results": []}, status=200)
    _reco(corpus, "a")

    rapport = enrich_tmdb.run(source="src", api_key="fake", ids={"a"})

    assert rapport.servies == set()
    assert [c.raison for c in rapport.introuvables] == ["not_found"]


# ===== simulation ============================================================
@responses.activate
def test_dry_run_writes_nothing_but_reports(corpus):
    _tmdb_repond()
    chemin = _reco(corpus, "a")
    avant = chemin.read_text(encoding="utf-8")

    rapport = enrich_tmdb.run(source="src", api_key="fake", ids={"a"}, apply=False)

    assert rapport.servies == {"a"} and rapport.ecrites == 0
    assert chemin.read_text(encoding="utf-8") == avant


@responses.activate
def test_the_cli_honours_dry_run(corpus, monkeypatch):
    _tmdb_repond()
    chemin = _reco(corpus, "a")
    avant = chemin.read_text(encoding="utf-8")
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    monkeypatch.setattr(sys, "argv",
                        ["enrich_tmdb.py", "--source", "src", "--ids", "a", "--dry-run"])

    enrich_tmdb.main()

    assert chemin.read_text(encoding="utf-8") == avant


@responses.activate
def test_the_cli_passes_the_ids_scope(corpus, monkeypatch):
    _tmdb_repond()
    _reco(corpus, "a")
    autre = _reco(corpus, "b")
    avant = autre.read_text(encoding="utf-8")
    monkeypatch.setenv("TMDB_API_KEY", "fake")
    monkeypatch.setattr(sys, "argv", ["enrich_tmdb.py", "--source", "src", "--ids", "a"])

    enrich_tmdb.main()

    assert autre.read_text(encoding="utf-8") == avant


# ===== clé API ===============================================================
def test_cle_api_says_where_to_put_the_key(monkeypatch):
    monkeypatch.setattr(enrich_tmdb, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="venus"):
        enrich_tmdb.cle_api()


def test_cle_api_returns_the_key(monkeypatch):
    monkeypatch.setattr(enrich_tmdb, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("TMDB_API_KEY", "fake")

    assert enrich_tmdb.cle_api() == "fake"


# ===== format de la liste d'ids =============================================
def test_ids_from_a_file_are_one_per_line(tmp_path):
    """Piège vécu : une liste séparée par des virgules dans un fichier ne filtre RIEN."""
    fichier = tmp_path / "ids.txt"
    fichier.write_text("# commentaire\nubm-1\n\nubm-2\n", encoding="utf-8")

    assert parse_ids_option(f"@{fichier}") == {"ubm-1", "ubm-2"}
    assert parse_ids_option("ubm-1, ubm-2") == {"ubm-1", "ubm-2"}
    assert parse_ids_option(None) == set()


def test_run_shares_a_session_when_given_one(corpus):
    """La chaîne peut fournir sa session ; sans reco à traiter, aucun appel."""
    session = requests.Session()
    assert enrich_tmdb.run(source="src", api_key="fake", session=session).vues == 0
