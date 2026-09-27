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

# Spotify et Qobuz se substituent dans les modules qui les portent : la façade
# ne fait que ré-exporter, la patcher n'aurait aucun effet.
import music_links_clients as clients
import music_links_pipeline as pipeline
import music_links_qobuz as qobuz

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
        {"url": "https://music.apple.com/fr/album/1"},
        {"url": "https://open.spotify.com/album/1"},
        {"url": "https://www.qobuz.com/fr-fr/album/x/1"}])
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
    # Un refus par plateforme visée : Deezer et Apple n'ont rien trouvé,
    # Spotify n'a pas d'identifiants et Qobuz est muet (cf. conftest).
    assert len(out.refusals) == 4
    assert [p for p, _r, _d in out.refusals][:2] == [m.PLATFORM_DEEZER,
                                                     m.PLATFORM_APPLE]


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


# ===== Spotify et Qobuz =====================================================
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"
SPOTIFY_API = "https://api.spotify.com/v1/search"
QOBUZ_RECHERCHE = "https://www.qobuz.com/fr-fr/search"
QOBUZ_HTML = "text/html; charset=utf-8"


def _rien_ailleurs():
    """Deezer et Apple muets : on n'éprouve ici que la nouvelle plateforme."""
    responses.add(responses.GET, f"{DEEZER}/search/album", json={"data": []},
                  status=200)
    responses.add(responses.GET, f"{ITUNES}/search", json={"results": []},
                  status=200)


def _spotify_disponible(monkeypatch):
    monkeypatch.setattr(pipeline, "spotify_credentials", lambda: ("id", "secret"))
    monkeypatch.setattr(clients, "spotify_credentials", lambda: ("id", "secret"))
    responses.add(responses.POST, SPOTIFY_TOKEN, status=200,
                  json={"access_token": "jeton", "expires_in": 3600})


@responses.activate
def test_resolve_reco_posts_a_spotify_link_when_corroborated(session, monkeypatch):
    _rien_ailleurs()
    _spotify_disponible(monkeypatch)
    responses.add(responses.GET, SPOTIFY_API, status=200, json={"albums": {"items": [
        {"id": "0syn", "name": "Civilisation", "artists": [{"name": "Orelsan"}],
         "external_urls": {"spotify": "https://open.spotify.com/album/0syn"}}]}})

    out = m.resolve_reco(ALBUM_RECO, session=session)

    assert [(link.platform, link.url) for link in out.links] == [
        (m.PLATFORM_SPOTIFY, "https://open.spotify.com/album/0syn")]


@responses.activate
def test_resolve_reco_refuses_a_spotify_homonym(session, monkeypatch):
    """Même titre, autre artiste : le garde-fou vaut pour Spotify comme pour Deezer."""
    _rien_ailleurs()
    _spotify_disponible(monkeypatch)
    responses.add(responses.GET, SPOTIFY_API, status=200, json={"albums": {"items": [
        {"id": "zzz", "name": "Civilisation", "artists": [{"name": "Autre Groupe"}],
         "external_urls": {"spotify": "https://open.spotify.com/album/zzz"}}]}})

    out = m.resolve_reco(ALBUM_RECO, session=session)

    assert out.links == ()
    assert (m.PLATFORM_SPOTIFY, m.REASON_ARTIST_MISMATCH) in [
        (p, r) for p, r, _d in out.refusals]


@responses.activate
def test_resolve_reco_says_when_spotify_is_not_configured(session):
    """Sur venus, les identifiants Spotify manquent : ce n'est pas une absence d'œuvre."""
    _rien_ailleurs()

    out = m.resolve_reco(ALBUM_RECO, session=session)

    assert (m.PLATFORM_SPOTIFY, m.REASON_NO_CREDENTIALS) in [
        (p, r) for p, r, _d in out.refusals]


@responses.activate
def test_resolve_reco_posts_a_qobuz_link_read_from_its_page(session, monkeypatch):
    """Bout en bout, avec le vrai client Qobuz : seul le réseau est simulé."""
    monkeypatch.setattr(pipeline, "qobuz_candidates", qobuz.candidates)
    _rien_ailleurs()
    responses.add(responses.GET, QOBUZ_RECHERCHE, status=200,
                  content_type=QOBUZ_HTML,
                  body='<a href="/fr-fr/album/civilisation/0123">x</a>')
    responses.add(responses.GET, "https://www.qobuz.com/fr-fr/album/civilisation/0123",
                  status=200, content_type=QOBUZ_HTML,
                  body='<script type="application/ld+json">'
                       '{"@type":"Product","name":"Civilisation",'
                       '"brand":{"@type":"Brand","name":"Orelsan"}}</script>')

    out = m.resolve_reco(ALBUM_RECO, session=session)

    assert [(link.platform, link.url) for link in out.links] == [
        (m.PLATFORM_QOBUZ,
         "https://www.qobuz.com/fr-fr/album/civilisation/0123")]


@responses.activate
def test_resolve_reco_refuses_a_qobuz_page_about_someone_else(session, monkeypatch):
    monkeypatch.setattr(pipeline, "qobuz_candidates", qobuz.candidates)
    _rien_ailleurs()
    responses.add(responses.GET, QOBUZ_RECHERCHE, status=200,
                  content_type=QOBUZ_HTML,
                  body='<a href="/fr-fr/album/autre/0999">x</a>')
    responses.add(responses.GET, "https://www.qobuz.com/fr-fr/album/autre/0999",
                  status=200, content_type=QOBUZ_HTML,
                  body='<script type="application/ld+json">'
                       '{"@type":"Product","name":"Civilisation",'
                       '"brand":{"@type":"Brand","name":"Quelqu\'un d\'autre"}}</script>')

    out = m.resolve_reco(ALBUM_RECO, session=session)

    assert out.links == ()
    assert (m.PLATFORM_QOBUZ, m.REASON_ARTIST_MISMATCH) in [
        (p, r) for p, r, _d in out.refusals]


@responses.activate
def test_resolve_reco_leaves_an_existing_qobuz_link_alone(session, monkeypatch):
    """Un lien posé à la main n'est jamais réinterrogé ni remplacé."""
    appels = []
    monkeypatch.setattr(pipeline, "qobuz_candidates",
                        lambda *a, **k: appels.append(a) or [])
    _rien_ailleurs()
    reco = dict(ALBUM_RECO, links=[
        {"url": "https://www.qobuz.com/fr-fr/album/deja/1"}])

    m.resolve_reco(reco, session=session)

    assert appels == []


# ===== l'interrupteur ========================================================
@pytest.mark.parametrize("valeur,actif", [
    ("0", False), ("off", False), ("OFF", False), ("false", False),
    ("no", False), ("non", False), (" 0 ", False),
    ("1", True), ("on", True), ("", True), ("oui", True),
])
def test_qobuz_enabled_reads_the_switch(monkeypatch, valeur, actif):
    monkeypatch.setenv(qobuz.ENV_SWITCH, valeur)
    assert qobuz.enabled() is actif


def test_qobuz_enabled_by_default(monkeypatch):
    """Absence de variable = plateforme active : l'interrupteur sert à COUPER."""
    monkeypatch.delenv(qobuz.ENV_SWITCH, raising=False)
    assert qobuz.enabled() is True


@responses.activate
def test_resolve_reco_does_not_even_query_qobuz_when_switched_off(session,
                                                                 monkeypatch):
    """Coupé, Qobuz n'est pas interrogé — on n'ouvre pas ses pages pour rien."""
    appels = []
    monkeypatch.setattr(pipeline, "qobuz_candidates",
                        lambda *a, **k: appels.append(a) or [])
    monkeypatch.setenv(qobuz.ENV_SWITCH, "0")
    _rien_ailleurs()

    out = m.resolve_reco(ALBUM_RECO, session=session)

    assert appels == []
    assert m.PLATFORM_QOBUZ not in [p for p, _r, _d in out.refusals]


@responses.activate
def test_resolve_reco_says_qobuz_was_disabled_when_it_was_the_only_gap(
        session, monkeypatch):
    """Sans cette raison, le rapport dirait « aucun lien » : on croirait que
    Qobuz ne connaît pas l'œuvre, alors qu'il n'a pas été interrogé."""
    monkeypatch.setenv(qobuz.ENV_SWITCH, "0")
    reco = dict(ALBUM_RECO, links=[
        {"url": "https://www.deezer.com/album/1"},
        {"url": "https://music.apple.com/fr/album/x/9"},
        {"url": "https://open.spotify.com/album/abc"},
    ])

    out = m.resolve_reco(reco, session=session)

    assert out.links == ()
    assert out.reason == m.REASON_QOBUZ_DISABLED


@responses.activate
def test_the_other_platforms_still_work_when_qobuz_is_off(session, monkeypatch):
    """Couper Qobuz ne doit rien casser d'autre."""
    monkeypatch.setenv(qobuz.ENV_SWITCH, "0")
    responses.add(responses.GET, f"{DEEZER}/search/album", status=200,
                  json={"data": [_deezer_album()]})
    responses.add(responses.GET, f"{ITUNES}/search", json={"results": []},
                  status=200)

    out = m.resolve_reco(ALBUM_RECO, session=session)

    assert [link.platform for link in out.links] == [m.PLATFORM_DEEZER]
