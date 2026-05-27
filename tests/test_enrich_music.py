"""Tests pour `tools/enrich_music.py` (Deezer + Spotify)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import requests
import responses

import enrich_music


# ===== Deezer ===============================================================
@responses.activate
@pytest.mark.parametrize("kind", ["track", "album", "artist"])
def test_deezer_search_returns_first_hit(kind):
    responses.add(
        responses.GET,
        f"https://api.deezer.com/search/{kind}",
        json={"data": [{"link": f"https://deezer.com/{kind}/1"}]},
        status=200,
    )
    hit = enrich_music.deezer_search(requests.Session(), kind, "q")
    assert hit["link"].endswith(f"/{kind}/1")


@responses.activate
def test_deezer_search_no_results_returns_none():
    responses.add(
        responses.GET, "https://api.deezer.com/search/track",
        json={"data": []}, status=200,
    )
    assert enrich_music.deezer_search(requests.Session(), "track", "q") is None


@responses.activate
def test_deezer_search_http_error_returns_none():
    responses.add(
        responses.GET, "https://api.deezer.com/search/track",
        json={}, status=500,
    )
    assert enrich_music.deezer_search(requests.Session(), "track", "q") is None


def test_deezer_search_request_exception_returns_none(monkeypatch):
    s = requests.Session()
    monkeypatch.setattr(s, "get",
                        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError()))
    assert enrich_music.deezer_search(s, "track", "q") is None


@responses.activate
def test_deezer_url_for_album_uses_album_endpoint():
    responses.add(
        responses.GET, "https://api.deezer.com/search/album",
        json={"data": [{"link": "https://deezer.com/album/9"}]}, status=200,
    )
    out = enrich_music.deezer_url_for("album", "Discovery", "Daft Punk", requests.Session())
    assert out == "https://deezer.com/album/9"


@responses.activate
def test_deezer_url_for_artist_uses_artist_endpoint():
    responses.add(
        responses.GET, "https://api.deezer.com/search/artist",
        json={"data": [{"link": "https://deezer.com/artist/5"}]}, status=200,
    )
    out = enrich_music.deezer_url_for("artiste", "Daft Punk", None, requests.Session())
    assert out == "https://deezer.com/artist/5"


@responses.activate
def test_deezer_url_for_musique_falls_back_through_kinds():
    """type=musique : track vide → album → renvoie l'album."""
    responses.add(
        responses.GET, "https://api.deezer.com/search/track",
        json={"data": []}, status=200,
    )
    responses.add(
        responses.GET, "https://api.deezer.com/search/album",
        json={"data": [{"link": "https://deezer.com/album/3"}]}, status=200,
    )
    out = enrich_music.deezer_url_for("musique", "One More Time", None, requests.Session())
    assert out == "https://deezer.com/album/3"


@responses.activate
def test_deezer_url_for_nothing_found():
    for kind in ("track", "album", "artist"):
        responses.add(
            responses.GET, f"https://api.deezer.com/search/{kind}",
            json={"data": []}, status=200,
        )
    assert enrich_music.deezer_url_for("musique", "X", None, requests.Session()) is None


# ===== Spotify ==============================================================
@responses.activate
def test_spotify_token_success():
    responses.add(
        responses.POST, "https://accounts.spotify.com/api/token",
        json={"access_token": "tok"}, status=200,
    )
    assert enrich_music.spotify_token(requests.Session(), "id", "sec") == "tok"


@responses.activate
def test_spotify_token_http_error_returns_none():
    responses.add(
        responses.POST, "https://accounts.spotify.com/api/token",
        json={"error": "bad"}, status=400,
    )
    assert enrich_music.spotify_token(requests.Session(), "id", "sec") is None


def test_spotify_token_request_exception(monkeypatch):
    s = requests.Session()
    monkeypatch.setattr(s, "post",
                        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError()))
    assert enrich_music.spotify_token(s, "id", "sec") is None


@responses.activate
def test_spotify_search_returns_first_item():
    responses.add(
        responses.GET, "https://api.spotify.com/v1/search",
        json={"tracks": {"items": [{"external_urls": {"spotify": "https://spot/track/1"}}]}},
        status=200,
    )
    hit = enrich_music.spotify_search(requests.Session(), "tok", "track", "q")
    assert hit["external_urls"]["spotify"].endswith("/track/1")


@responses.activate
def test_spotify_search_401_token_invalid_returns_none():
    responses.add(
        responses.GET, "https://api.spotify.com/v1/search",
        json={"error": "expired"}, status=401,
    )
    assert enrich_music.spotify_search(requests.Session(), "tok", "track", "q") is None


@responses.activate
def test_spotify_search_403_premium_required():
    responses.add(
        responses.GET, "https://api.spotify.com/v1/search",
        json={"error": "premium required"}, status=403,
    )
    assert enrich_music.spotify_search(requests.Session(), "tok", "track", "q") is None


def test_spotify_search_request_exception(monkeypatch):
    s = requests.Session()
    monkeypatch.setattr(s, "get",
                        lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError()))
    assert enrich_music.spotify_search(s, "tok", "track", "q") is None


@responses.activate
def test_spotify_search_empty_items_returns_none():
    responses.add(
        responses.GET, "https://api.spotify.com/v1/search",
        json={"tracks": {"items": []}}, status=200,
    )
    assert enrich_music.spotify_search(requests.Session(), "tok", "track", "q") is None


@responses.activate
def test_spotify_url_for_album():
    responses.add(
        responses.GET, "https://api.spotify.com/v1/search",
        json={"albums": {"items": [{"external_urls": {"spotify": "https://spot/album/1"}}]}},
        status=200,
    )
    out = enrich_music.spotify_url_for("album", "Discovery", "Daft Punk",
                                       requests.Session(), "tok")
    assert out == "https://spot/album/1"


@responses.activate
def test_spotify_url_for_artist_falls_through_when_no_external_url():
    """Le 1ᵉʳ hit a un dict sans 'external_urls' → on continue (renvoie None ici)."""
    responses.add(
        responses.GET, "https://api.spotify.com/v1/search",
        json={"artists": {"items": [{}]}}, status=200,
    )
    out = enrich_music.spotify_url_for("artiste", "X", None, requests.Session(), "tok")
    assert out is None


@responses.activate
def test_spotify_url_for_musique_cascades():
    """track vide, album avec hit → renvoie l'URL album."""
    # responses match toutes les GET sur /search ; on enchaîne 2 réponses.
    responses.add(
        responses.GET, "https://api.spotify.com/v1/search",
        json={"tracks": {"items": []}}, status=200,
    )
    responses.add(
        responses.GET, "https://api.spotify.com/v1/search",
        json={"albums": {"items": [{"external_urls": {"spotify": "https://s/album/1"}}]}},
        status=200,
    )
    out = enrich_music.spotify_url_for("musique", "X", None, requests.Session(), "tok")
    assert out == "https://s/album/1"


# ===== main() ===============================================================
@pytest.fixture
def reco_env(tmp_path, monkeypatch):
    recos_dir = tmp_path / "recos"
    recos_dir.mkdir()
    monkeypatch.setattr(enrich_music, "recos_dir_for", lambda s: recos_dir)
    monkeypatch.setattr(enrich_music.time, "sleep", lambda *_: None)
    monkeypatch.setattr(enrich_music, "load_dotenv", lambda *a, **k: None)
    return recos_dir


def _w(d, name, data):
    (d / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@responses.activate
def test_main_deezer_only_no_spotify_env(reco_env, monkeypatch):
    """Sans SPOTIFY_CLIENT_ID/SECRET, on enrichit seulement Deezer."""
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    _w(reco_env, "a.json", {"id": "a", "type": "musique", "title": "One More Time"})
    # Type non ciblé ignoré.
    _w(reco_env, "b.json", {"id": "b", "type": "film", "title": "X"})

    responses.add(
        responses.GET, "https://api.deezer.com/search/track",
        json={"data": [{"link": "https://deezer/track/1"}]}, status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_music.py", "--source", "src"])
    enrich_music.main()
    out = json.loads((reco_env / "a.json").read_text("utf-8"))
    assert out["externalIds"]["deezer"] == "https://deezer/track/1"
    assert "spotify" not in out["externalIds"]


@responses.activate
def test_main_with_spotify_token_ok(reco_env, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "sec")
    _w(reco_env, "a.json", {"id": "a", "type": "album", "title": "Discovery",
                            "creator": "Daft Punk"})
    # Token OK + markets probe OK.
    responses.add(
        responses.POST, "https://accounts.spotify.com/api/token",
        json={"access_token": "tok"}, status=200,
    )
    responses.add(
        responses.GET, "https://api.spotify.com/v1/markets",
        json={"markets": ["FR"]}, status=200,
    )
    # Deezer album search.
    responses.add(
        responses.GET, "https://api.deezer.com/search/album",
        json={"data": [{"link": "https://deezer/album/1"}]}, status=200,
    )
    # Spotify album search.
    responses.add(
        responses.GET, "https://api.spotify.com/v1/search",
        json={"albums": {"items": [{"external_urls": {"spotify": "https://spot/album/9"}}]}},
        status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_music.py", "--source", "src"])
    enrich_music.main()
    out = json.loads((reco_env / "a.json").read_text("utf-8"))
    assert out["externalIds"]["deezer"].endswith("/album/1")
    assert out["externalIds"]["spotify"].endswith("/album/9")


@responses.activate
def test_main_spotify_token_ok_but_probe_403_disables_spotify(reco_env, monkeypatch):
    """Token OK + /markets renvoie 403 → on continue Deezer seul."""
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "sec")
    _w(reco_env, "a.json", {"id": "a", "type": "musique", "title": "X"})
    responses.add(
        responses.POST, "https://accounts.spotify.com/api/token",
        json={"access_token": "tok"}, status=200,
    )
    responses.add(
        responses.GET, "https://api.spotify.com/v1/markets",
        json={"error": "premium"}, status=403,
    )
    responses.add(
        responses.GET, "https://api.deezer.com/search/track",
        json={"data": [{"link": "https://deezer/track/1"}]}, status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_music.py", "--source", "src"])
    enrich_music.main()
    out = json.loads((reco_env / "a.json").read_text("utf-8"))
    assert "spotify" not in out["externalIds"]
    assert out["externalIds"]["deezer"].endswith("/track/1")


@responses.activate
def test_main_spotify_token_fails(reco_env, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "sec")
    _w(reco_env, "a.json", {"id": "a", "type": "musique", "title": "X"})
    responses.add(
        responses.POST, "https://accounts.spotify.com/api/token",
        json={"error": "bad"}, status=400,
    )
    # Pas de probe attendu, mais Deezer si.
    responses.add(
        responses.GET, "https://api.deezer.com/search/track",
        json={"data": []}, status=200,
    )
    responses.add(
        responses.GET, "https://api.deezer.com/search/album",
        json={"data": []}, status=200,
    )
    responses.add(
        responses.GET, "https://api.deezer.com/search/artist",
        json={"data": []}, status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_music.py", "--source", "src"])
    enrich_music.main()


@responses.activate
def test_main_limit_and_skip_already_enriched(reco_env, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    # Sans token, on skippe si deezer déjà présent.
    _w(reco_env, "a.json", {"id": "a", "type": "musique", "title": "X",
                            "externalIds": {"deezer": "https://d/1"}})
    _w(reco_env, "b.json", {"id": "b", "type": "musique", "title": "Y"})
    _w(reco_env, "c.json", {"id": "c", "type": "musique", "title": "Z"})
    responses.add(
        responses.GET, "https://api.deezer.com/search/track",
        json={"data": [{"link": "https://d/2"}]}, status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_music.py", "--source", "src", "--limit", "1"])
    enrich_music.main()
    # b a été enrichi, c non.
    b = json.loads((reco_env / "b.json").read_text("utf-8"))
    c = json.loads((reco_env / "c.json").read_text("utf-8"))
    assert b["externalIds"]["deezer"] == "https://d/2"
    assert "externalIds" not in c


def test_main_no_targets_returns_early(reco_env, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(sys, "argv", ["enrich_music.py", "--source", "src"])
    enrich_music.main()


@responses.activate
def test_main_force_replaces_existing(reco_env, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    _w(reco_env, "a.json", {"id": "a", "type": "musique", "title": "X",
                            "externalIds": {"deezer": "https://old"}})
    responses.add(
        responses.GET, "https://api.deezer.com/search/track",
        json={"data": [{"link": "https://new"}]}, status=200,
    )
    monkeypatch.setattr(sys, "argv", ["enrich_music.py", "--source", "src", "--force"])
    enrich_music.main()
    out = json.loads((reco_env / "a.json").read_text("utf-8"))
    assert out["externalIds"]["deezer"] == "https://new"


@responses.activate
def test_main_deezer_not_found_logs(reco_env, monkeypatch):
    """Couvre la branche 'pas trouvé' de la boucle main."""
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    _w(reco_env, "a.json", {"id": "a", "type": "musique", "title": "X"})
    for k in ("track", "album", "artist"):
        responses.add(
            responses.GET, f"https://api.deezer.com/search/{k}",
            json={"data": []}, status=200,
        )
    monkeypatch.setattr(sys, "argv", ["enrich_music.py", "--source", "src"])
    enrich_music.main()
    out = json.loads((reco_env / "a.json").read_text("utf-8"))
    assert "externalIds" not in out


@responses.activate
def test_main_spotify_not_found_for_reco(reco_env, monkeypatch):
    """Token Spotify OK, Deezer trouve, Spotify ne trouve pas → branche logique."""
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "sec")
    _w(reco_env, "a.json", {"id": "a", "type": "musique", "title": "X"})
    responses.add(
        responses.POST, "https://accounts.spotify.com/api/token",
        json={"access_token": "tok"}, status=200,
    )
    responses.add(
        responses.GET, "https://api.spotify.com/v1/markets",
        json={}, status=200,
    )
    responses.add(
        responses.GET, "https://api.deezer.com/search/track",
        json={"data": [{"link": "https://d/1"}]}, status=200,
    )
    # 3 essais spotify (track, album, artist) tous vides.
    for _ in range(3):
        responses.add(
            responses.GET, "https://api.spotify.com/v1/search",
            json={"tracks": {"items": []}, "albums": {"items": []},
                  "artists": {"items": []}}, status=200,
        )
    monkeypatch.setattr(sys, "argv", ["enrich_music.py", "--source", "src"])
    enrich_music.main()
    out = json.loads((reco_env / "a.json").read_text("utf-8"))
    assert out["externalIds"]["deezer"] == "https://d/1"
    assert "spotify" not in out["externalIds"]
