"""Tests des clients réseau (MOCKÉS) et de `resolve_video_links`.

Aucun appel réel : tout passe par `responses`. On vérifie surtout les
GARDE-FOUS, car la règle est « zéro invention » — au moindre doute (titre
distant contradictoire, homonyme, erreur HTTP) on n'écrit aucun lien et on
laisse une raison traçable.
"""
from __future__ import annotations

import pytest
import requests
import responses

import enrich_video_links as evl

TMDB = "https://api.themoviedb.org/3"


@pytest.fixture()
def session():
    return requests.Session()


def _movie(**over):
    payload = {
        "id": 597,
        "title": "Titanic",
        "release_date": "1997-12-19",
        "external_ids": {"imdb_id": "tt0120338"},
        "watch/providers": {
            "results": {"FR": {"link": "https://www.justwatch.com/fr/film/titanic"}},
        },
    }
    payload.update(over)
    return payload


def _tv(**over):
    payload = {
        "id": 1396,
        "name": "Breaking Bad",
        "first_air_date": "2008-01-20",
        "external_ids": {"imdb_id": "tt0903747"},
        "watch/providers": {
            "results": {"FR": {"link": "https://www.justwatch.com/fr/serie/breaking-bad"}},
        },
    }
    payload.update(over)
    return payload


# ===== fetch_tmdb_detail ====================================================
@responses.activate
def test_fetch_tmdb_detail_movie_appends_external_ids_and_providers(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", json=_movie(), status=200)
    data = evl.fetch_tmdb_detail(session, "movie", "597", api_key="k")
    assert data["external_ids"]["imdb_id"] == "tt0120338"
    appended = responses.calls[0].request.params["append_to_response"]
    assert appended == "external_ids,watch/providers"


@responses.activate
def test_fetch_tmdb_detail_tv(session):
    responses.add(responses.GET, f"{TMDB}/tv/1396", json=_tv(), status=200)
    assert evl.fetch_tmdb_detail(session, "tv", "1396", api_key="k")["id"] == 1396


@responses.activate
def test_fetch_tmdb_detail_http_error_returns_none(session):
    responses.add(responses.GET, f"{TMDB}/movie/1", json={}, status=404)
    assert evl.fetch_tmdb_detail(session, "movie", "1", api_key="k") is None


# ===== Population « id existant » ===========================================
@responses.activate
def test_resolve_from_id_returns_three_links(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", json=_movie(), status=200)
    reco = {"title": "Titanic", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    res = evl.resolve_video_links(reco, session=session, api_key="k")
    assert res.reason == evl.REASON_FILLED
    assert res.population == evl.POPULATION_ID
    assert res.source == "tmdb:movie/597"
    assert [link["url"] for link in res.links] == [
        "https://www.imdb.com/title/tt0120338/",
        "https://www.themoviedb.org/movie/597",
        "https://www.justwatch.com/fr/film/titanic",
    ]


@responses.activate
def test_resolve_from_id_tv_branch(session):
    responses.add(responses.GET, f"{TMDB}/tv/1396", json=_tv(), status=200)
    reco = {"title": "Breaking Bad", "types": ["serie"],
            "externalIds": {"tmdb": "1396", "tmdbType": "tv"}}
    res = evl.resolve_video_links(reco, session=session, api_key="k")
    assert res.reason == evl.REASON_FILLED
    assert res.links[1]["url"] == "https://www.themoviedb.org/tv/1396"


@responses.activate
def test_resolve_from_id_http_error(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", json={}, status=500)
    reco = {"title": "Titanic", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    res = evl.resolve_video_links(reco, session=session, api_key="k")
    assert res.reason == evl.REASON_HTTP_ERROR
    assert res.links == ()


@responses.activate
def test_resolve_from_id_title_mismatch_writes_nothing(session):
    """L'id externe a été posé par recherche de titre : il peut être FAUX."""
    responses.add(responses.GET, f"{TMDB}/movie/597",
                  json=_movie(title="Mortal Kombat"), status=200)
    reco = {"title": "Mortal", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    res = evl.resolve_video_links(reco, session=session, api_key="k")
    assert res.reason == evl.REASON_TITLE_MISMATCH
    assert "Mortal Kombat" in res.detail
    assert res.links == ()


@responses.activate
def test_resolve_from_id_accepts_payload_without_any_title(session):
    responses.add(responses.GET, f"{TMDB}/movie/597",
                  json={"id": 597, "external_ids": {"imdb_id": "tt1"}}, status=200)
    reco = {"title": "Titanic", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    res = evl.resolve_video_links(reco, session=session, api_key="k")
    assert res.reason == evl.REASON_FILLED


@responses.activate
def test_resolve_from_id_year_mismatch(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", json=_movie(), status=200)
    reco = {"title": "Titanic", "year": 2020, "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    res = evl.resolve_video_links(reco, session=session, api_key="k")
    assert res.reason == evl.REASON_YEAR_MISMATCH
    assert "1997" in res.detail


@responses.activate
def test_resolve_from_id_released_after_episode(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", json=_movie(), status=200)
    reco = {"title": "Titanic", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    res = evl.resolve_video_links(reco, session=session, api_key="k", episode_year=1990)
    assert res.reason == evl.REASON_RELEASED_AFTER_EPISODE


@responses.activate
def test_resolve_from_id_no_new_link_when_all_hosts_covered(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", json=_movie(), status=200)
    reco = {"title": "Titanic", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"},
            "links": [
                {"label": "IMDb", "url": "https://www.imdb.com/title/tt0120338/"},
                {"label": "TMDB", "url": "https://www.themoviedb.org/movie/597"},
                {"label": "JustWatch", "url": "https://www.justwatch.com/fr/film/titanic"},
            ]}
    res = evl.resolve_video_links(reco, session=session, api_key="k")
    assert res.reason == evl.REASON_NO_NEW_LINK
    assert res.links == ()


@responses.activate
def test_resolve_from_id_partial_when_one_host_covered(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", json=_movie(), status=200)
    reco = {"title": "Titanic", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"},
            "links": [{"label": "IMDb", "url": "https://www.imdb.com/title/tt0120338/"}]}
    res = evl.resolve_video_links(reco, session=session, api_key="k")
    assert [link["label"] for link in res.links] == ["TMDB", "Où regarder"]


@responses.activate
def test_resolve_from_id_respects_site_selection(session):
    responses.add(responses.GET, f"{TMDB}/movie/597", json=_movie(), status=200)
    reco = {"title": "Titanic", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    res = evl.resolve_video_links(reco, session=session, api_key="k",
                                  sites=(evl.SITE_IMDB,))
    assert [link["label"] for link in res.links] == ["IMDb"]


def test_resolve_without_api_key_refuses(session):
    reco = {"title": "Titanic", "types": ["film"],
            "externalIds": {"tmdb": "597", "tmdbType": "movie"}}
    res = evl.resolve_video_links(reco, session=session, api_key=None)
    assert res.reason == evl.REASON_NO_API_KEY


def test_resolve_returns_plan_refusal_untouched(session):
    res = evl.resolve_video_links({"types": ["livre"]}, session=session, api_key="k")
    assert res.reason == evl.REASON_TYPE_UNSUPPORTED
    assert res.source is None
    assert res.population is None


# ===== Population « recherche » =============================================
def _search(kind, results):
    responses.add(responses.GET, f"{TMDB}/search/{kind}",
                  json={"results": results}, status=200)


@responses.activate
def test_resolve_from_search_happy_path(session):
    _search("movie", [{"id": 597, "title": "Titanic", "release_date": "1997-12-19",
                       "popularity": 40.0}])
    responses.add(responses.GET, f"{TMDB}/movie/597", json=_movie(), status=200)
    reco = {"title": "Titanic", "types": ["film"]}
    res = evl.resolve_video_links(reco, session=session, api_key="k", allow_search=True)
    assert res.reason == evl.REASON_FILLED
    assert res.population == evl.POPULATION_SEARCH
    assert len(res.links) == 3


@responses.activate
def test_resolve_from_search_tv_branch(session):
    _search("tv", [{"id": 1396, "name": "Breaking Bad",
                    "first_air_date": "2008-01-20", "popularity": 60.0}])
    responses.add(responses.GET, f"{TMDB}/tv/1396", json=_tv(), status=200)
    reco = {"title": "Breaking Bad", "types": ["serie"]}
    res = evl.resolve_video_links(reco, session=session, api_key="k", allow_search=True)
    assert res.reason == evl.REASON_FILLED
    assert res.source == "tmdb:tv/1396"


@responses.activate
def test_resolve_from_search_http_error(session):
    responses.add(responses.GET, f"{TMDB}/search/movie", json={}, status=500)
    res = evl.resolve_video_links({"title": "X", "types": ["film"]},
                                  session=session, api_key="k", allow_search=True)
    assert res.reason == evl.REASON_HTTP_ERROR
    assert res.source == "tmdb-search:movie"


@responses.activate
def test_resolve_from_search_no_exact_title_match(session):
    """« Mortal » ne doit PAS ramener « Mortal Kombat » : égalité stricte exigée."""
    _search("movie", [{"id": 9, "title": "Mortal Kombat", "popularity": 50.0}])
    res = evl.resolve_video_links({"title": "Mortal", "types": ["film"]},
                                  session=session, api_key="k", allow_search=True)
    assert res.reason == evl.REASON_SEARCH_NO_MATCH


@responses.activate
def test_resolve_from_search_ambiguous_two_works_same_title(session):
    _search("movie", [{"id": 1, "title": "Cargo", "popularity": 10.0},
                      {"id": 2, "title": "Cargo", "popularity": 9.0}])
    res = evl.resolve_video_links({"title": "Cargo", "types": ["film"]},
                                  session=session, api_key="k", allow_search=True)
    assert res.reason == evl.REASON_SEARCH_AMBIGUOUS
    assert "1, 2" in res.detail


@responses.activate
def test_resolve_from_search_too_obscure(session):
    _search("movie", [{"id": 3, "title": "Amélie", "popularity": 0.14}])
    res = evl.resolve_video_links({"title": "Amélie", "types": ["film"]},
                                  session=session, api_key="k", allow_search=True)
    assert res.reason == evl.REASON_SEARCH_TOO_OBSCURE
    assert "0.14" in res.detail


@responses.activate
def test_resolve_from_search_eclipsed_by_a_far_more_popular_work(session):
    _search("movie", [
        {"id": 4, "title": "Le Seigneur des Anneaux", "popularity": 4.44},
        {"id": 5, "title": "Le Seigneur des Anneaux : Le Retour du roi",
         "popularity": 52.0},
    ])
    res = evl.resolve_video_links({"title": "Le Seigneur des Anneaux", "types": ["film"]},
                                  session=session, api_key="k", allow_search=True)
    assert res.reason == evl.REASON_SEARCH_ECLIPSED


@responses.activate
def test_resolve_from_search_year_filter_removes_candidate(session):
    _search("movie", [{"id": 6, "title": "Titanic", "release_date": "2020-01-01",
                       "popularity": 30.0}])
    res = evl.resolve_video_links({"title": "Titanic", "year": 1997, "types": ["film"]},
                                  session=session, api_key="k", allow_search=True)
    assert res.reason == evl.REASON_SEARCH_NO_MATCH


@responses.activate
def test_resolve_from_search_anachronism_filter_removes_candidate(session):
    _search("movie", [{"id": 7, "title": "Mourir seul", "release_date": "2025-01-01",
                       "popularity": 30.0}])
    res = evl.resolve_video_links({"title": "Mourir seul", "types": ["film"]},
                                  session=session, api_key="k", allow_search=True,
                                  episode_year=2021)
    assert res.reason == evl.REASON_SEARCH_NO_MATCH


@responses.activate
def test_resolve_from_search_rechecks_full_record(session):
    """La fiche complète repasse par les garde-fous : un titre contradictoire tue."""
    _search("movie", [{"id": 597, "title": "Titanic", "popularity": 40.0}])
    responses.add(responses.GET, f"{TMDB}/movie/597",
                  json=_movie(title="Autre chose entièrement"), status=200)
    res = evl.resolve_video_links({"title": "Titanic", "types": ["film"]},
                                  session=session, api_key="k", allow_search=True)
    assert res.reason == evl.REASON_TITLE_MISMATCH


@responses.activate
def test_resolve_from_search_passes_year_to_the_api(session):
    _search("movie", [{"id": 597, "title": "Titanic", "release_date": "1997-12-19",
                       "popularity": 40.0}])
    responses.add(responses.GET, f"{TMDB}/movie/597", json=_movie(), status=200)
    evl.resolve_video_links({"title": "Titanic", "year": 1997, "types": ["film"]},
                            session=session, api_key="k", allow_search=True)
    assert responses.calls[0].request.params["year"] == "1997"
