"""Tests des clients réseau (MOCKÉS) et de la normalisation des payloads.

Aucun appel réel : tout passe par `responses`. Les payloads reproduisent la
forme réelle des réponses Deezer et iTunes, y compris leurs pièges — Deezer
répond HTTP 200 avec `{"error": …}` pour un identifiant inexistant.
"""
from __future__ import annotations

import pytest
import requests
import responses

# La couche réseau vit dans son propre module depuis la scission : c'est
# LUI qu'on importe, sinon substituer `time.sleep` viserait la façade et
# les tests de réessai sur 429 attendraient réellement cinq secondes.
import music_links_clients as m

DEEZER = "https://api.deezer.com"
ITUNES = "https://itunes.apple.com"


@pytest.fixture()
def session():
    return requests.Session()


# ===== get_json =============================================================
@responses.activate
def test_get_json_success(session):
    responses.add(responses.GET, "https://x.test/a", json={"ok": 1}, status=200)
    assert m.get_json(session, "https://x.test/a") == {"ok": 1}


@responses.activate
def test_get_json_http_error_returns_none(session):
    responses.add(responses.GET, "https://x.test/a", json={}, status=500)
    assert m.get_json(session, "https://x.test/a") is None


@responses.activate
def test_get_json_non_json_body_returns_none(session):
    responses.add(responses.GET, "https://x.test/a", body="<html>", status=200)
    assert m.get_json(session, "https://x.test/a") is None


@responses.activate
def test_get_json_non_dict_body_returns_none(session):
    responses.add(responses.GET, "https://x.test/a", json=[1, 2], status=200)
    assert m.get_json(session, "https://x.test/a") is None


def test_get_json_request_exception_returns_none(session, monkeypatch):
    def _boom(*_a, **_kw):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(session, "get", _boom)
    assert m.get_json(session, "https://x.test/a") is None


@responses.activate
def test_get_json_retries_once_after_429(session, monkeypatch):
    """Un 429 non réessayé se déguiserait en « aucun résultat »."""
    slept: list[float] = []
    monkeypatch.setattr(m.time, "sleep", slept.append)
    responses.add(responses.GET, "https://x.test/a", json={}, status=429)
    responses.add(responses.GET, "https://x.test/a", json={"ok": 1}, status=200)
    assert m.get_json(session, "https://x.test/a") == {"ok": 1}
    assert slept == [m.RETRY_AFTER_SLEEP]


@responses.activate
def test_get_json_gives_up_after_the_retry(session, monkeypatch):
    monkeypatch.setattr(m.time, "sleep", lambda _s: None)
    responses.add(responses.GET, "https://x.test/a", json={}, status=429)
    responses.add(responses.GET, "https://x.test/a", json={}, status=429)
    assert m.get_json(session, "https://x.test/a") is None


# ===== deezer_search ========================================================
@responses.activate
def test_deezer_search_returns_data(session):
    responses.add(responses.GET, f"{DEEZER}/search/album",
                  json={"data": [{"id": 1, "title": "Civilisation"}]}, status=200)
    assert m.deezer_search(session, "album", "Civilisation Orelsan")[0]["id"] == 1


@responses.activate
def test_deezer_search_error_payload_is_empty(session):
    """Deezer signale ses erreurs en HTTP 200 avec une clé `error`."""
    responses.add(responses.GET, f"{DEEZER}/search/album",
                  json={"error": {"type": "Exception"}}, status=200)
    assert m.deezer_search(session, "album", "x") == []


@responses.activate
def test_deezer_search_http_error_is_empty(session):
    responses.add(responses.GET, f"{DEEZER}/search/album", json={}, status=503)
    assert m.deezer_search(session, "album", "x") == []


@responses.activate
def test_deezer_search_non_list_data_is_empty(session):
    responses.add(responses.GET, f"{DEEZER}/search/album",
                  json={"data": "nope"}, status=200)
    assert m.deezer_search(session, "album", "x") == []


# ===== deezer_by_id =========================================================
@responses.activate
def test_deezer_by_id_returns_payload(session):
    responses.add(responses.GET, f"{DEEZER}/album/42",
                  json={"id": 42, "title": "T"}, status=200)
    assert m.deezer_by_id(session, "album", "42")["title"] == "T"


@responses.activate
def test_deezer_by_id_error_payload_is_none(session):
    responses.add(responses.GET, f"{DEEZER}/album/42",
                  json={"error": {"code": 800}}, status=200)
    assert m.deezer_by_id(session, "album", "42") is None


@responses.activate
def test_deezer_by_id_http_error_is_none(session):
    responses.add(responses.GET, f"{DEEZER}/album/42", json={}, status=404)
    assert m.deezer_by_id(session, "album", "42") is None


# ===== itunes_search ========================================================
@responses.activate
def test_itunes_search_returns_results(session):
    responses.add(responses.GET, f"{ITUNES}/search",
                  json={"resultCount": 1, "results": [{"artistName": "Orelsan"}]},
                  status=200)
    assert m.itunes_search(session, "album", "x")[0]["artistName"] == "Orelsan"


@responses.activate
def test_itunes_search_http_error_is_empty(session):
    responses.add(responses.GET, f"{ITUNES}/search", json={}, status=500)
    assert m.itunes_search(session, "album", "x") == []


@responses.activate
def test_itunes_search_non_list_results_is_empty(session):
    responses.add(responses.GET, f"{ITUNES}/search",
                  json={"results": None}, status=200)
    assert m.itunes_search(session, "album", "x") == []


# ===== deezer_candidate =====================================================
def test_deezer_candidate_album():
    cand = m.deezer_candidate(
        {"id": 262200072, "title": "Civilisation", "link": "https://deezer.com/a",
         "artist": {"name": "Orelsan"}}, "album")
    assert (cand.platform, cand.kind) == (m.PLATFORM_DEEZER, "album")
    assert (cand.title, cand.artist, cand.ident) == (
        "Civilisation", "Orelsan", "262200072")


def test_deezer_candidate_artist_uses_name_field():
    cand = m.deezer_candidate(
        {"id": 7, "name": "Gorillaz", "link": "https://deezer.com/artist/7"},
        "artist")
    assert (cand.artist, cand.title) == ("Gorillaz", "")


def test_deezer_candidate_artist_falls_back_to_nested_artist():
    cand = m.deezer_candidate(
        {"id": 7, "link": "https://d/7", "artist": {"name": "Gorillaz"}}, "artist")
    assert cand.artist == "Gorillaz"


def test_deezer_candidate_without_link_is_none():
    """Sans URL renvoyée, il faudrait la fabriquer — la doctrine l'interdit."""
    assert m.deezer_candidate({"id": 1, "title": "X"}, "album") is None


def test_deezer_candidate_missing_artist_is_empty_string():
    cand = m.deezer_candidate({"id": 1, "title": "X", "link": "https://d/1"},
                              "album")
    assert cand.artist == ""


# ===== itunes_candidate =====================================================
def test_itunes_candidate_album():
    cand = m.itunes_candidate(
        {"collectionId": 999, "collectionName": "Civilisation",
         "artistName": "Orelsan",
         "collectionViewUrl": "https://music.apple.com/fr/album/x/999"}, "album")
    assert (cand.platform, cand.title, cand.ident) == (
        m.PLATFORM_APPLE, "Civilisation", "999")


def test_itunes_candidate_track():
    cand = m.itunes_candidate(
        {"collectionId": 5, "trackName": "Basique", "artistName": "Orelsan",
         "trackViewUrl": "https://music.apple.com/fr/album/basique/5"}, "track")
    assert cand.title == "Basique"


def test_itunes_candidate_artist():
    cand = m.itunes_candidate(
        {"artistId": 12, "artistName": "Gorillaz",
         "artistViewUrl": "https://music.apple.com/fr/artist/12"}, "artist")
    assert (cand.artist, cand.title, cand.ident) == ("Gorillaz", "", "12")


def test_itunes_candidate_without_url_is_none():
    assert m.itunes_candidate({"collectionName": "X"}, "album") is None


def test_itunes_candidate_missing_artist_name():
    cand = m.itunes_candidate(
        {"collectionId": 1, "collectionName": "X",
         "collectionViewUrl": "https://music.apple.com/a"}, "album")
    assert cand.artist == ""
