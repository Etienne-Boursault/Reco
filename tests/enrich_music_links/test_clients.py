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


# ===== Spotify ==============================================================
# Référence prise AVANT que le décor (conftest) ne remplace l'attribut du
# module : c'est la vraie fonction qu'on éprouve ici.
_vraies_identifiants = m.spotify_credentials
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"
SPOTIFY_API = "https://api.spotify.com/v1/search"


def _identifiants(monkeypatch, paire=("id", "secret")):
    monkeypatch.setattr(m, "spotify_credentials", lambda: paire)


def test_spotify_credentials_none_when_environment_is_bare(monkeypatch, tmp_path):
    """Sans variables NI fichier .env : la machine n'est pas configurée.

    `TOOLS_DIR` est détourné vers un dossier vide, sinon le `.env` du poste
    reviendrait par `load_dotenv` et le test dépendrait de la machine.
    """
    monkeypatch.setattr(m, "TOOLS_DIR", tmp_path)
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)

    assert _vraies_identifiants() is None


def test_spotify_credentials_read_from_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "TOOLS_DIR", tmp_path)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "abc")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "def")

    assert _vraies_identifiants() == ("abc", "def")


@responses.activate
def test_spotify_token_is_fetched_once_and_cached(session, monkeypatch):
    """Un jeton vaut une heure : le redemander à chaque reco serait absurde."""
    _identifiants(monkeypatch)
    responses.add(responses.POST, SPOTIFY_TOKEN, status=200,
                  json={"access_token": "jeton", "expires_in": 3600})

    assert m.spotify_token(session) == "jeton"
    assert m.spotify_token(session) == "jeton"
    assert len(responses.calls) == 1


@responses.activate
def test_spotify_token_none_on_http_error(session, monkeypatch):
    _identifiants(monkeypatch)
    responses.add(responses.POST, SPOTIFY_TOKEN, status=400, json={})

    assert m.spotify_token(session) is None


@responses.activate
def test_spotify_token_none_when_payload_has_no_token(session, monkeypatch):
    _identifiants(monkeypatch)
    responses.add(responses.POST, SPOTIFY_TOKEN, status=200, json={"scope": ""})

    assert m.spotify_token(session) is None


@responses.activate
def test_spotify_token_none_on_non_json_answer(session, monkeypatch):
    _identifiants(monkeypatch)
    responses.add(responses.POST, SPOTIFY_TOKEN, status=200, body="<html>")

    assert m.spotify_token(session) is None


def test_spotify_token_none_on_network_failure(session, monkeypatch):
    _identifiants(monkeypatch)
    with responses.RequestsMock():
        assert m.spotify_token(session) is None


def test_spotify_token_none_without_credentials(session, monkeypatch):
    monkeypatch.setattr(m, "spotify_credentials", lambda: None)
    assert m.spotify_token(session) is None


@responses.activate
def test_spotify_search_returns_items(session, monkeypatch):
    _identifiants(monkeypatch)
    responses.add(responses.POST, SPOTIFY_TOKEN, status=200,
                  json={"access_token": "jeton", "expires_in": 3600})
    responses.add(responses.GET, SPOTIFY_API, status=200,
                  json={"albums": {"items": [{"id": "1"}, "pas un objet"]}})

    assert m.spotify_search(session, "album", "Civilisation Orelsan") == [{"id": "1"}]


@responses.activate
def test_spotify_search_empty_when_subscription_expires(session, monkeypatch):
    """403 « Active premium subscription required » : panne attendue, pas un plantage."""
    _identifiants(monkeypatch)
    responses.add(responses.POST, SPOTIFY_TOKEN, status=200,
                  json={"access_token": "jeton", "expires_in": 3600})
    responses.add(responses.GET, SPOTIFY_API, status=403, json={"error": {}})

    assert m.spotify_search(session, "album", "x") == []


def test_spotify_search_empty_without_token(session, monkeypatch):
    monkeypatch.setattr(m, "spotify_credentials", lambda: None)
    assert m.spotify_search(session, "album", "x") == []


@responses.activate
def test_spotify_search_empty_when_shape_is_unexpected(session, monkeypatch):
    _identifiants(monkeypatch)
    responses.add(responses.POST, SPOTIFY_TOKEN, status=200,
                  json={"access_token": "jeton", "expires_in": 3600})
    responses.add(responses.GET, SPOTIFY_API, status=200, json={"albums": {}})

    assert m.spotify_search(session, "album", "x") == []


def test_spotify_candidate_album_keeps_only_the_main_artist():
    """« Ben Mazué, Yoa » ferait dériver la comparaison : on garde le premier."""
    cand = m.spotify_candidate(
        {"id": "2Gv", "name": "Rupture",
         "artists": [{"name": "Ben Mazué"}, {"name": "Yoa"}],
         "external_urls": {"spotify": "https://open.spotify.com/album/2Gv"}},
        "album")

    assert (cand.artist, cand.title, cand.ident) == ("Ben Mazué", "Rupture", "2Gv")
    assert cand.platform == m.PLATFORM_SPOTIFY


def test_spotify_candidate_artist_uses_its_own_name():
    cand = m.spotify_candidate(
        {"id": "73B", "name": "Ben Mazué",
         "external_urls": {"spotify": "https://open.spotify.com/artist/73B"}},
        "artist")

    assert (cand.artist, cand.title) == ("Ben Mazué", "")


def test_spotify_candidate_without_url_is_none():
    assert m.spotify_candidate({"id": "1", "name": "x"}, "album") is None


def test_spotify_candidate_missing_artists_is_empty_string():
    cand = m.spotify_candidate(
        {"id": "1", "name": "x",
         "external_urls": {"spotify": "https://open.spotify.com/album/1"}}, "album")

    assert cand.artist == ""
