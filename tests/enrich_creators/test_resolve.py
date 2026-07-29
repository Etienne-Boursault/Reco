"""Tests des clients réseau (MOCKÉS) et de `resolve_creator`.

Aucun appel réel : tout passe par `responses`. On vérifie surtout les
GARDE-FOUS — la règle du projet est « zéro invention » : au moindre doute
(titre distant qui ne correspond pas, payload vide, erreur HTTP), on laisse
le `creator` vide avec une raison traçable.
"""
from __future__ import annotations

import pytest
import requests
import responses

import enrich_creators as ec

TMDB = "https://api.themoviedb.org/3"
DEEZER = "https://api.deezer.com"
OL = "https://openlibrary.org"


@pytest.fixture()
def session():
    return requests.Session()


# ===== get_json (client bas niveau) ========================================
@responses.activate
def test_get_json_success(session):
    responses.add(responses.GET, "https://x.test/a", json={"ok": 1}, status=200)
    assert ec.get_json(session, "https://x.test/a") == {"ok": 1}


@responses.activate
def test_get_json_http_error_returns_none(session):
    responses.add(responses.GET, "https://x.test/a", json={}, status=404)
    assert ec.get_json(session, "https://x.test/a") is None


@responses.activate
def test_get_json_invalid_body_returns_none(session):
    responses.add(responses.GET, "https://x.test/a", body="<html>nope", status=200)
    assert ec.get_json(session, "https://x.test/a") is None


def test_get_json_request_exception_returns_none(session, monkeypatch):
    monkeypatch.setattr(session, "get", lambda *a, **kw: (_ for _ in ()).throw(
        requests.ConnectionError("boom")))
    assert ec.get_json(session, "https://x.test/a") is None


@responses.activate
def test_get_json_non_dict_body_returns_none(session):
    responses.add(responses.GET, "https://x.test/a", json=[1, 2], status=200)
    assert ec.get_json(session, "https://x.test/a") is None


# ===== Clients dédiés =======================================================
@responses.activate
def test_fetch_tmdb_movie_appends_credits(session):
    responses.add(responses.GET, f"{TMDB}/movie/597",
                  json={"title": "Titanic", "credits": {"crew": []}}, status=200)
    out = ec.fetch_tmdb_movie(session, "597", api_key="k")
    assert out["title"] == "Titanic"
    req = responses.calls[0].request
    assert "append_to_response=credits" in req.url
    assert "api_key=k" in req.url
    assert "language=fr-FR" in req.url


@responses.activate
def test_fetch_tmdb_tv(session):
    responses.add(responses.GET, f"{TMDB}/tv/1396",
                  json={"name": "Breaking Bad", "created_by": []}, status=200)
    assert ec.fetch_tmdb_tv(session, "1396", api_key="k")["name"] == "Breaking Bad"


@responses.activate
def test_fetch_deezer_ok(session):
    responses.add(responses.GET, f"{DEEZER}/track/1",
                  json={"title": "T", "artist": {"name": "A"}}, status=200)
    assert ec.fetch_deezer(session, "track", "1")["artist"]["name"] == "A"


@responses.activate
def test_fetch_deezer_error_payload_is_none(session):
    """Deezer répond 200 avec `{"error": …}` pour un id inexistant."""
    responses.add(responses.GET, f"{DEEZER}/track/999",
                  json={"error": {"type": "DataException", "message": "no data"}},
                  status=200)
    assert ec.fetch_deezer(session, "track", "999") is None


@responses.activate
def test_fetch_openlibrary_edition(session):
    responses.add(responses.GET, f"{OL}/isbn/9782070360024.json",
                  json={"title": "L'Étranger"}, status=200)
    assert ec.fetch_openlibrary_edition(session, "9782070360024")["title"] == "L'Étranger"


@responses.activate
def test_fetch_openlibrary_author(session):
    responses.add(responses.GET, f"{OL}/authors/OL1A.json",
                  json={"name": "Albert Camus"}, status=200)
    assert ec.fetch_openlibrary_author(session, "/authors/OL1A")["name"] == "Albert Camus"


# ===== resolve_creator — TMDB movie ========================================
def _reco(**kw):
    base = {"id": "ubm-0001", "title": "Titanic", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    base.update(kw)
    return base


@responses.activate
def test_resolve_movie_fills_director(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", status=200, json={
        "title": "Titanic", "release_date": "1997-12-19",
        "credits": {"crew": [{"job": "Director", "name": "James Cameron"}]},
    })
    r = ec.resolve_creator(_reco(), session=session, api_key="k")
    assert r.creator == "James Cameron"
    assert r.reason == ec.REASON_FILLED
    assert r.source == "tmdb:movie/597"


@responses.activate
def test_resolve_movie_title_mismatch_leaves_empty(session):
    """L'id TMDB pointe vers une autre œuvre → on n'écrit RIEN."""
    responses.add(responses.GET, f"{TMDB}/movie/597", status=200, json={
        "title": "Un tout autre film", "original_title": "Something Else",
        "credits": {"crew": [{"job": "Director", "name": "Quelqu'un"}]},
    })
    r = ec.resolve_creator(_reco(), session=session, api_key="k")
    assert r.creator is None
    assert r.reason == ec.REASON_TITLE_MISMATCH
    assert "Un tout autre film" in r.detail


@responses.activate
def test_resolve_movie_year_mismatch_leaves_empty(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", status=200, json={
        "title": "Titanic", "release_date": "1953-01-01",
        "credits": {"crew": [{"job": "Director", "name": "Jean Negulesco"}]},
    })
    r = ec.resolve_creator(_reco(year=1997), session=session, api_key="k")
    assert r.creator is None
    assert r.reason == ec.REASON_YEAR_MISMATCH


@responses.activate
def test_resolve_movie_released_after_episode_leaves_empty(session):
    """Un film de 2025 ne peut pas être recommandé dans un épisode de 2021 :
    l'identifiant pointe forcément vers une autre œuvre."""
    responses.add(responses.GET, f"{TMDB}/movie/597", status=200, json={
        "title": "Titanic", "release_date": "2025-01-01",
        "credits": {"crew": [{"job": "Director", "name": "Quelqu'un"}]},
    })
    r = ec.resolve_creator(_reco(), session=session, api_key="k", episode_year=2021)
    assert r.creator is None
    assert r.reason == ec.REASON_RELEASED_AFTER_EPISODE
    assert "2025" in r.detail


@responses.activate
def test_resolve_movie_released_same_year_as_episode_is_kept(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", status=200, json={
        "title": "Titanic", "release_date": "2026-01-01",
        "credits": {"crew": [{"job": "Director", "name": "X"}]},
    })
    r = ec.resolve_creator(_reco(), session=session, api_key="k", episode_year=2026)
    assert r.creator == "X"


@responses.activate
def test_resolve_movie_without_episode_year_skips_the_check(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", status=200, json={
        "title": "Titanic", "release_date": "2025-01-01",
        "credits": {"crew": [{"job": "Director", "name": "X"}]},
    })
    assert ec.resolve_creator(_reco(), session=session, api_key="k").creator == "X"


@responses.activate
def test_resolve_movie_no_director(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", status=200, json={
        "title": "Titanic", "credits": {"crew": [{"job": "Writer", "name": "X"}]},
    })
    r = ec.resolve_creator(_reco(), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_NO_DIRECTOR


@responses.activate
def test_resolve_movie_http_error(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", status=500, json={})
    r = ec.resolve_creator(_reco(), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_HTTP_ERROR


# ===== resolve_creator — TMDB tv ===========================================
@responses.activate
def test_resolve_tv_fills_created_by(session):
    responses.add(responses.GET, f"{TMDB}/tv/1396", status=200, json={
        "name": "Breaking Bad", "created_by": [{"name": "Vince Gilligan"}]})
    reco = _reco(title="Breaking Bad", types=["serie"],
                 externalIds={"tmdb": "1396", "tmdbType": "tv"})
    r = ec.resolve_creator(reco, session=session, api_key="k")
    assert r.creator == "Vince Gilligan"
    assert r.source == "tmdb:tv/1396"


@responses.activate
def test_resolve_tv_without_created_by(session):
    """Docu-série / téléréalité : TMDB n'a pas de `created_by` → vide."""
    responses.add(responses.GET, f"{TMDB}/tv/1396", status=200,
                  json={"name": "Breaking Bad", "created_by": []})
    reco = _reco(title="Breaking Bad", types=["serie"],
                 externalIds={"tmdb": "1396", "tmdbType": "tv"})
    r = ec.resolve_creator(reco, session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_NO_CREATED_BY


@responses.activate
def test_resolve_tv_title_mismatch(session):
    responses.add(responses.GET, f"{TMDB}/tv/1396", status=200, json={
        "name": "Autre série", "created_by": [{"name": "X"}]})
    reco = _reco(title="Breaking Bad", types=["serie"],
                 externalIds={"tmdb": "1396", "tmdbType": "tv"})
    r = ec.resolve_creator(reco, session=session, api_key="k")
    assert r.reason == ec.REASON_TITLE_MISMATCH


# ===== resolve_creator — Deezer ============================================
def _music(**kw):
    base = {"id": "ubm-0320", "title": "Étincelle Vol 2", "types": ["album"],
            "externalIds": {"deezer": "https://www.deezer.com/album/356500427"}}
    base.update(kw)
    return base


@responses.activate
def test_resolve_deezer_album_fills_artist(session):
    responses.add(responses.GET, f"{DEEZER}/album/356500427", status=200,
                  json={"title": "Étincelle Vol 2", "artist": {"name": "Lucie Antunes"}})
    r = ec.resolve_creator(_music(), session=session, api_key="k")
    assert r.creator == "Lucie Antunes"
    assert r.source == "deezer:album/356500427"


@responses.activate
def test_resolve_deezer_title_mismatch(session):
    responses.add(responses.GET, f"{DEEZER}/album/356500427", status=200,
                  json={"title": "Un autre disque", "artist": {"name": "X"}})
    r = ec.resolve_creator(_music(), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_TITLE_MISMATCH


@responses.activate
def test_resolve_deezer_artist_equal_to_title_is_refused(session):
    """Reco « Madonna » typée musique : l'artiste répète le titre → inutile
    et dangereux (homonymie possible). On laisse vide."""
    responses.add(responses.GET, f"{DEEZER}/track/1", status=200,
                  json={"title": "Madonna", "artist": {"name": "Madonna"}})
    reco = _music(title="Madonna", types=["musique"],
                  externalIds={"deezer": "https://www.deezer.com/track/1"})
    r = ec.resolve_creator(reco, session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_CREATOR_EQUALS_TITLE


def test_resolve_deezer_artist_url_is_refused(session):
    """URL /artist/ : le « créateur » serait l'œuvre elle-même."""
    reco = _music(title="Al'Tarba", types=["artiste", "album"],
                  externalIds={"deezer": "https://www.deezer.com/artist/201875"})
    r = ec.resolve_creator(reco, session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_DEEZER_ARTIST_URL


def test_resolve_deezer_unparsable_url(session):
    reco = _music(externalIds={"deezer": "https://www.deezer.com/nope"})
    r = ec.resolve_creator(reco, session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_DEEZER_BAD_URL


@responses.activate
def test_resolve_deezer_http_error(session):
    responses.add(responses.GET, f"{DEEZER}/album/356500427", status=200,
                  json={"error": {"message": "nope"}})
    r = ec.resolve_creator(_music(), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_HTTP_ERROR


@responses.activate
def test_resolve_deezer_no_artist_field(session):
    responses.add(responses.GET, f"{DEEZER}/album/356500427", status=200,
                  json={"title": "Étincelle Vol 2"})
    r = ec.resolve_creator(_music(), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_NO_ARTIST


# ===== resolve_creator — OpenLibrary =======================================
def _book(**kw):
    base = {"id": "ubm-0900", "title": "L'Étranger", "types": ["livre"],
            "externalIds": {"isbn": "9782070360024"}}
    base.update(kw)
    return base


@responses.activate
def test_resolve_openlibrary_fills_author(session):
    responses.add(responses.GET, f"{OL}/isbn/9782070360024.json", status=200,
                  json={"title": "L'Étranger", "authors": [{"key": "/authors/OL1A"}]})
    responses.add(responses.GET, f"{OL}/authors/OL1A.json", status=200,
                  json={"name": "Albert Camus"})
    r = ec.resolve_creator(_book(), session=session, api_key="k")
    assert r.creator == "Albert Camus"
    assert r.source == "openlibrary:9782070360024"


@responses.activate
def test_resolve_openlibrary_multiple_authors(session):
    responses.add(responses.GET, f"{OL}/isbn/1.json", status=200, json={
        "title": "Watchmen",
        "authors": [{"key": "/authors/OL1A"}, {"key": "/authors/OL2A"}]})
    responses.add(responses.GET, f"{OL}/authors/OL1A.json", status=200,
                  json={"name": "Alan Moore"})
    responses.add(responses.GET, f"{OL}/authors/OL2A.json", status=200,
                  json={"name": "Dave Gibbons"})
    r = ec.resolve_creator(_book(title="Watchmen", types=["bd"],
                                 externalIds={"isbn": "1"}),
                           session=session, api_key="k")
    assert r.creator == "Alan Moore, Dave Gibbons"


@responses.activate
def test_resolve_openlibrary_edition_not_found(session):
    responses.add(responses.GET, f"{OL}/isbn/9782070360024.json", status=404, json={})
    r = ec.resolve_creator(_book(), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_HTTP_ERROR


@responses.activate
def test_resolve_openlibrary_no_authors(session):
    responses.add(responses.GET, f"{OL}/isbn/9782070360024.json", status=200,
                  json={"title": "L'Étranger"})
    r = ec.resolve_creator(_book(), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_NO_AUTHOR


@responses.activate
def test_resolve_openlibrary_author_doc_unreachable(session):
    responses.add(responses.GET, f"{OL}/isbn/9782070360024.json", status=200,
                  json={"title": "L'Étranger", "authors": [{"key": "/authors/OL1A"}]})
    responses.add(responses.GET, f"{OL}/authors/OL1A.json", status=500, json={})
    r = ec.resolve_creator(_book(), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_NO_AUTHOR


@responses.activate
def test_resolve_openlibrary_title_mismatch(session):
    responses.add(responses.GET, f"{OL}/isbn/9782070360024.json", status=200,
                  json={"title": "Un tout autre livre",
                        "authors": [{"key": "/authors/OL1A"}]})
    r = ec.resolve_creator(_book(), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_TITLE_MISMATCH


@responses.activate
def test_resolve_openlibrary_without_title_still_fills(session):
    """OpenLibrary sans titre : rien à contredire, l'ISBN est un identifiant
    fort → on accepte."""
    responses.add(responses.GET, f"{OL}/isbn/9782070360024.json", status=200,
                  json={"authors": [{"key": "/authors/OL1A"}]})
    responses.add(responses.GET, f"{OL}/authors/OL1A.json", status=200,
                  json={"name": "Albert Camus"})
    r = ec.resolve_creator(_book(), session=session, api_key="k")
    assert r.creator == "Albert Camus"


# ===== resolve_creator — court-circuits ====================================
def test_resolve_skips_when_creator_present(session):
    r = ec.resolve_creator(_reco(creator="Déjà"), session=session, api_key="k")
    assert r.creator is None and r.reason == ec.REASON_ALREADY_SET


def test_resolve_skips_unsupported_type(session):
    r = ec.resolve_creator({"id": "x", "title": "T", "types": ["podcast"]},
                           session=session, api_key="k")
    assert r.reason == ec.REASON_TYPE_UNSUPPORTED


def test_resolve_tmdb_movie_without_api_key_is_skipped(session):
    r = ec.resolve_creator(_reco(), session=session, api_key=None)
    assert r.creator is None and r.reason == ec.REASON_NO_API_KEY


def test_resolve_tmdb_tv_without_api_key_is_skipped(session):
    reco = _reco(types=["serie"], externalIds={"tmdb": "1396", "tmdbType": "tv"})
    r = ec.resolve_creator(reco, session=session, api_key=None)
    assert r.creator is None and r.reason == ec.REASON_NO_API_KEY


@responses.activate
def test_resolve_deezer_works_without_api_key(session):
    """Deezer et OpenLibrary n'ont pas besoin de clé."""
    responses.add(responses.GET, f"{DEEZER}/album/356500427", status=200,
                  json={"title": "Étincelle Vol 2", "artist": {"name": "Lucie Antunes"}})
    r = ec.resolve_creator(_music(), session=session, api_key=None)
    assert r.creator == "Lucie Antunes"
