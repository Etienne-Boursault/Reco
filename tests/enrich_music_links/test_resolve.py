"""Tests de la résolution d'UNE reco : recherche, promotion d'identifiant,
et enchaînement des garde-fous. Réseau entièrement mocké via `responses`.

Le fil rouge : chaque test qui produit un lien montre POURQUOI il est sûr
(titre ET artiste corroborés) ; chaque test qui n'en produit pas montre la
raison traçable du refus.
"""
from __future__ import annotations

import pytest
import requests
import responses

import enrich_music_links as m

DEEZER = "https://api.deezer.com"
ITUNES = "https://itunes.apple.com"


@pytest.fixture()
def session():
    return requests.Session()


def _deezer_album(id_=1, title="Civilisation", artist="Orelsan"):
    return {"id": id_, "title": title, "link": f"https://www.deezer.com/album/{id_}",
            "artist": {"name": artist}}


def _itunes_album(id_=9, title="Civilisation", artist="Orelsan"):
    return {"collectionId": id_, "collectionName": title, "artistName": artist,
            "collectionViewUrl": f"https://music.apple.com/fr/album/x/{id_}"}


ALBUM_RECO = {"id": "ubm-1", "title": "Civilisation", "creator": "Orelsan",
              "types": ["album"], "status": "validated"}


# ===== _resolve_search ======================================================
@responses.activate
def test_resolve_search_deezer_success(session):
    responses.add(responses.GET, f"{DEEZER}/search/album",
                  json={"data": [_deezer_album()]}, status=200)
    res = m._resolve_search(ALBUM_RECO, session,
                            platform=m.PLATFORM_DEEZER, kind="album")
    assert res.reason == m.REASON_LINKED
    assert res.link.url == "https://www.deezer.com/album/1"
    assert res.link.source == "deezer:album/1"
    assert res.link.label == "Deezer"


@responses.activate
def test_resolve_search_apple_success(session):
    responses.add(responses.GET, f"{ITUNES}/search",
                  json={"results": [_itunes_album()]}, status=200)
    res = m._resolve_search(ALBUM_RECO, session,
                            platform=m.PLATFORM_APPLE, kind="album")
    assert res.link.label == "Apple Music"
    assert res.link.url.startswith("https://music.apple.com/")


@responses.activate
def test_resolve_search_refuses_wrong_artist(session):
    """Deezer renvoie bien un « Civilisation », mais pas celui d'Orelsan."""
    responses.add(responses.GET, f"{DEEZER}/search/album",
                  json={"data": [_deezer_album(artist="Autre Groupe")]}, status=200)
    res = m._resolve_search(ALBUM_RECO, session,
                            platform=m.PLATFORM_DEEZER, kind="album")
    assert res.link is None
    assert res.reason == m.REASON_ARTIST_MISMATCH


@responses.activate
def test_resolve_search_empty_results(session):
    responses.add(responses.GET, f"{DEEZER}/search/album",
                  json={"data": []}, status=200)
    res = m._resolve_search(ALBUM_RECO, session,
                            platform=m.PLATFORM_DEEZER, kind="album")
    assert (res.link, res.reason) == (None, m.REASON_NO_MATCH)


@responses.activate
def test_resolve_search_drops_results_without_url(session):
    responses.add(responses.GET, f"{DEEZER}/search/album",
                  json={"data": [{"id": 1, "title": "Civilisation",
                                  "artist": {"name": "Orelsan"}}]}, status=200)
    res = m._resolve_search(ALBUM_RECO, session,
                            platform=m.PLATFORM_DEEZER, kind="album")
    assert res.link is None


@responses.activate
def test_resolve_search_artist_page_targets_the_artist_endpoint(session):
    """Une reco d'ARTISTE vise la page artiste, jamais un morceau."""
    responses.add(responses.GET, f"{DEEZER}/search/artist",
                  json={"data": [{"id": 7, "name": "Gorillaz",
                                  "link": "https://www.deezer.com/artist/7"}]},
                  status=200)
    reco = {"id": "x", "title": "Gorillaz", "types": ["artiste"]}
    res = m._resolve_search(reco, session, platform=m.PLATFORM_DEEZER,
                            kind="artist")
    assert res.link.url == "https://www.deezer.com/artist/7"


# ===== _resolve_promote_deezer ==============================================
@responses.activate
def test_promote_deezer_id_success(session):
    responses.add(responses.GET, f"{DEEZER}/album/262200072",
                  json=_deezer_album(262200072), status=200)
    reco = dict(ALBUM_RECO,
                externalIds={"deezer": "https://www.deezer.com/album/262200072"})
    res = m._resolve_promote_deezer(reco, session, expected_kind="album")
    assert res.reason == m.REASON_LINKED
    assert res.link.source == "deezer:album/262200072"


@responses.activate
def test_promote_deezer_id_rejects_wrong_stored_id(session):
    """L'identifiant vient d'une passe non vérifiée : il peut être faux."""
    responses.add(responses.GET, f"{DEEZER}/album/999",
                  json=_deezer_album(999, title="Un tout autre album"),
                  status=200)
    reco = dict(ALBUM_RECO,
                externalIds={"deezer": "https://www.deezer.com/album/999"})
    res = m._resolve_promote_deezer(reco, session, expected_kind="album")
    assert (res.link, res.reason) == (None, m.REASON_TITLE_MISMATCH)


def test_promote_deezer_id_unparsable_url(session):
    reco = dict(ALBUM_RECO, externalIds={"deezer": "https://exemple.test/x"})
    res = m._resolve_promote_deezer(reco, session, expected_kind="album")
    assert (res.link, res.reason) == (None, m.REASON_BAD_DEEZER_URL)


def test_promote_deezer_id_refuses_a_stored_artist_page_for_an_album(session):
    """Une reco d'album doit mener à un album, pas à la page de l'artiste.

    Cas réels : ubm-1081 « Clou » et ubm-1135 « Winnterzuko » portaient un
    identifiant d'ARTISTE, l'ancienne passe ayant rabattu sa recherche.
    """
    reco = dict(ALBUM_RECO,
                externalIds={"deezer": "https://www.deezer.com/artist/77163"})
    res = m._resolve_promote_deezer(reco, session, expected_kind="album")
    assert (res.link, res.reason) == (None, m.REASON_STORED_KIND_MISMATCH)
    assert "artist" in res.detail


@responses.activate
def test_promote_deezer_id_http_error(session):
    responses.add(responses.GET, f"{DEEZER}/album/1", json={}, status=500)
    reco = dict(ALBUM_RECO,
                externalIds={"deezer": "https://www.deezer.com/album/1"})
    res = m._resolve_promote_deezer(reco, session, expected_kind="album")
    assert (res.link, res.reason) == (None, m.REASON_HTTP_ERROR)


@responses.activate
def test_promote_deezer_id_payload_without_link(session):
    responses.add(responses.GET, f"{DEEZER}/album/1",
                  json={"id": 1, "title": "Civilisation"}, status=200)
    reco = dict(ALBUM_RECO,
                externalIds={"deezer": "https://www.deezer.com/album/1"})
    res = m._resolve_promote_deezer(reco, session, expected_kind="album")
    assert (res.link, res.reason) == (None, m.REASON_NO_MATCH)


# ===== resolve_reco =========================================================
def test_resolve_reco_refuses_non_musical_type(session):
    out = m.resolve_reco({"types": ["film"], "title": "X"}, session=session)
    assert (out.links, out.reason) == ((), m.REASON_TYPE_UNSUPPORTED)


def test_resolve_reco_refuses_artiste_without_opt_in(session):
    out = m.resolve_reco({"types": ["artiste"], "title": "Vérino"},
                         session=session)
    assert out.reason == m.REASON_ARTIST_TYPE_UNPROVEN


def test_resolve_reco_already_complete(session):
    reco = dict(ALBUM_RECO, links=[
        {"url": "https://www.deezer.com/album/1"},
        {"url": "https://music.apple.com/fr/album/1"}])
    out = m.resolve_reco(reco, session=session)
    assert (out.links, out.reason) == ((), m.REASON_ALREADY_COMPLETE)


def test_resolve_reco_refuses_without_creator(session):
    """Sans artiste, il n'y a rien contre quoi corroborer un titre."""
    out = m.resolve_reco({"types": ["album"], "title": "Amélie",
                          "status": "validated"}, session=session)
    assert (out.links, out.reason) == ((), m.REASON_NO_CREATOR)


@responses.activate
def test_resolve_reco_artist_page_needs_no_creator(session):
    responses.add(responses.GET, f"{DEEZER}/search/artist",
                  json={"data": [{"id": 7, "name": "Gorillaz",
                                  "link": "https://www.deezer.com/artist/7"}]},
                  status=200)
    responses.add(responses.GET, f"{ITUNES}/search",
                  json={"results": []}, status=200)
    out = m.resolve_reco({"types": ["artiste"], "title": "Gorillaz"},
                         session=session, allow_artists=True)
    assert [link.platform for link in out.links] == [m.PLATFORM_DEEZER]


@responses.activate
def test_resolve_reco_fills_both_platforms(session):
    responses.add(responses.GET, f"{DEEZER}/search/album",
                  json={"data": [_deezer_album()]}, status=200)
    responses.add(responses.GET, f"{ITUNES}/search",
                  json={"results": [_itunes_album()]}, status=200)
    out = m.resolve_reco(ALBUM_RECO, session=session)
    assert sorted(link.platform for link in out.links) == [
        m.PLATFORM_APPLE, m.PLATFORM_DEEZER]
    assert out.reason == m.REASON_LINKED


@responses.activate
def test_resolve_reco_homogenises_only_the_missing_platform(session):
    """Le cœur de l'homogénéisation : Deezer présent, on ne cherche qu'Apple."""
    responses.add(responses.GET, f"{ITUNES}/search",
                  json={"results": [_itunes_album()]}, status=200)
    reco = dict(ALBUM_RECO, links=[{"url": "https://www.deezer.com/album/1"}])
    out = m.resolve_reco(reco, session=session)
    assert [link.platform for link in out.links] == [m.PLATFORM_APPLE]


@responses.activate
def test_resolve_reco_promotes_then_searches_apple(session):
    responses.add(responses.GET, f"{DEEZER}/album/5",
                  json=_deezer_album(5), status=200)
    responses.add(responses.GET, f"{ITUNES}/search",
                  json={"results": [_itunes_album()]}, status=200)
    reco = dict(ALBUM_RECO,
                externalIds={"deezer": "https://www.deezer.com/album/5"})
    out = m.resolve_reco(reco, session=session)
    assert sorted(link.platform for link in out.links) == [
        m.PLATFORM_APPLE, m.PLATFORM_DEEZER]


@responses.activate
def test_resolve_reco_reason_is_the_first_refusal(session):
    responses.add(responses.GET, f"{DEEZER}/search/album",
                  json={"data": []}, status=200)
    responses.add(responses.GET, f"{ITUNES}/search",
                  json={"results": []}, status=200)
    out = m.resolve_reco(ALBUM_RECO, session=session)
    assert out.links == ()
    assert out.reason == m.REASON_NO_MATCH
    assert len(out.refusals) == 2


@responses.activate
def test_resolve_reco_track_search_for_musique(session):
    responses.add(responses.GET, f"{DEEZER}/search/track",
                  json={"data": [{"id": 3, "title": "Basique",
                                  "link": "https://www.deezer.com/track/3",
                                  "artist": {"name": "Orelsan"}}]}, status=200)
    responses.add(responses.GET, f"{ITUNES}/search",
                  json={"results": []}, status=200)
    reco = {"id": "x", "title": "Basique", "creator": "Orelsan",
            "types": ["musique"], "status": "validated"}
    out = m.resolve_reco(reco, session=session)
    assert out.links[0].url == "https://www.deezer.com/track/3"
