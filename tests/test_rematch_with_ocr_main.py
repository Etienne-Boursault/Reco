"""Tests pour `tools/rematch_with_ocr.py` au-delà de `_episode_is_extract`.

Couvre `_download_thumb`, `_ocr_episode_number`, `_candidates`, `rematch()` et
`main()`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests
import responses

import rematch_with_ocr


# ===== _download_thumb ======================================================
@responses.activate
def test_download_thumb_max_ok():
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/abc/maxresdefault.jpg",
        body=big, status=200,
    )
    assert rematch_with_ocr._download_thumb("abc") == big


@responses.activate
def test_download_thumb_falls_back():
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/abc/maxresdefault.jpg",
        body=b"tiny", status=200,
    )
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/abc/hqdefault.jpg",
        body=big, status=200,
    )
    assert rematch_with_ocr._download_thumb("abc") == big


@responses.activate
def test_download_thumb_request_exception(monkeypatch):
    """Une RequestException sur maxres → on enchaîne sur hq."""
    big = b"\xff\xd8" + b"x" * 3000
    # Patch requests.get pour lever sur maxres puis renvoyer big sur hq.
    real_get = requests.get
    calls = {"n": 0}
    def fake(url, **kw):
        calls["n"] += 1
        if "maxresdefault" in url:
            raise requests.ConnectionError("boom")
        r = SimpleNamespace(ok=True, content=big)
        return r
    monkeypatch.setattr(rematch_with_ocr.requests, "get", fake)
    assert rematch_with_ocr._download_thumb("abc") == big
    assert calls["n"] == 2


@responses.activate
def test_download_thumb_all_fail():
    for q in ("maxresdefault", "hqdefault"):
        responses.add(
            responses.GET, f"https://i.ytimg.com/vi/abc/{q}.jpg",
            status=404,
        )
    assert rematch_with_ocr._download_thumb("abc") is None


# ===== _ocr_episode_number ==================================================
def _client_returning(text: str):
    block = SimpleNamespace(type="text", text=text)
    msg = SimpleNamespace(content=[block])
    c = MagicMock()
    c.messages.create.return_value = msg
    return c


@responses.activate
def test_ocr_returns_number():
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/v/maxresdefault.jpg",
        body=big, status=200,
    )
    assert rematch_with_ocr._ocr_episode_number(_client_returning("42"), "v") == 42


@responses.activate
def test_ocr_no_thumb_returns_none():
    for q in ("maxresdefault", "hqdefault"):
        responses.add(
            responses.GET, f"https://i.ytimg.com/vi/v/{q}.jpg", status=404,
        )
    assert rematch_with_ocr._ocr_episode_number(MagicMock(), "v") is None


@responses.activate
def test_ocr_no_digit_returns_none():
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/v/maxresdefault.jpg",
        body=big, status=200,
    )
    assert rematch_with_ocr._ocr_episode_number(_client_returning("NONE"), "v") is None


# ===== _candidates ==========================================================
def test_candidates_filters_short_videos_and_used():
    ep = {"title": "Episode 42 invité X"}
    videos = [
        {"id": "v1", "title": "EP 42 invité X", "duration": 60 * 60},
        {"id": "v2", "title": "Extrait", "duration": 5 * 60},  # trop court
        {"id": "v3", "title": "EP 42 — best moment", "duration": 50 * 60},
        {"id": "v4", "title": "déjà utilisé", "duration": 60 * 60},
    ]
    out = rematch_with_ocr._candidates(ep, videos, used_ids={"v4"})
    ids = [v["id"] for _, v in out]
    assert "v2" not in ids and "v4" not in ids
    # Triés par similarité décroissante.
    assert out[0][0] >= out[-1][0]


def test_candidates_no_title_returns_empty():
    assert rematch_with_ocr._candidates({"title": ""}, [], set()) == []


# ===== rematch() ============================================================
@pytest.fixture
def env(tmp_path, monkeypatch):
    eps_dir = tmp_path / "eps"
    eps_dir.mkdir()
    sources_dir = tmp_path / "src" / "content" / "sources"
    sources_dir.mkdir(parents=True)
    (sources_dir / "src.json").write_text(
        json.dumps({"id": "src", "youtubeChannel": "https://yt/@x"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(rematch_with_ocr, "list_episode_files",
                        lambda s: sorted(eps_dir.glob("*.json")))
    # rematch_with_ocr.rematch() utilise common.load_source qui lit dans
    # common.SOURCES_DIR (chemin absolu) — on redirige cette constante.
    import common
    monkeypatch.setattr(common, "SOURCES_DIR", sources_dir)
    return eps_dir


def _ep(d, name, data):
    (d / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_rematch_no_targets(env, monkeypatch):
    """Aucun épisode-extrait → rematch retourne sans appeler le client."""
    _ep(env, "a.json", {
        "guid": "g1", "title": "E",
        "youtubeUrl": "https://www.youtube.com/watch?v=full",
        "youtubeDuration": 60 * 60, "audioDuration": 60 * 60, "number": 1,
    })
    monkeypatch.setattr(rematch_with_ocr, "_fetch_channel_videos", lambda c: [])
    rematch_with_ocr.rematch("src", only_guid=None, dry_run=True)


def test_rematch_only_guid_dry_run_no_candidates(env, monkeypatch):
    _ep(env, "a.json", {
        "guid": "g1", "title": "Episode 7 test",
        "youtubeUrl": "https://www.youtube.com/watch?v=short",
        "youtubeDuration": 5 * 60, "audioDuration": 60 * 60, "number": 7,
    })
    monkeypatch.setattr(rematch_with_ocr, "_fetch_channel_videos", lambda c: [])
    # En dry-run, pas de _make_client appelé.
    rematch_with_ocr.rematch("src", only_guid="g1", dry_run=True)


def test_rematch_dry_run_lists_candidates_no_write(env, monkeypatch):
    _ep(env, "a.json", {
        "guid": "g1", "title": "Episode 7 invité X",
        "youtubeUrl": "https://www.youtube.com/watch?v=short",
        "youtubeDuration": 5 * 60, "audioDuration": 60 * 60, "number": 7,
    })
    videos = [
        {"id": "full1", "title": "Episode 7 invité X", "duration": 60 * 60},
    ]
    monkeypatch.setattr(rematch_with_ocr, "_fetch_channel_videos", lambda c: videos)
    rematch_with_ocr.rematch("src", only_guid=None, dry_run=True)
    # Dry-run : on n'écrit rien.
    out = json.loads((env / "a.json").read_text("utf-8"))
    assert out["youtubeUrl"].endswith("v=short")


@responses.activate
def test_rematch_applies_match_when_ocr_matches(env, monkeypatch):
    _ep(env, "a.json", {
        "guid": "g1", "title": "Episode 7 invité X",
        "youtubeUrl": "https://www.youtube.com/watch?v=short",
        "youtubeDuration": 5 * 60, "audioDuration": 60 * 60, "number": 7,
    })
    videos = [
        {"id": "full1", "title": "Episode 7 invité X", "duration": 60 * 60},
    ]
    monkeypatch.setattr(rematch_with_ocr, "_fetch_channel_videos", lambda c: videos)
    # Thumb OK + OCR=7.
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/full1/maxresdefault.jpg",
        body=big, status=200,
    )
    import common
    monkeypatch.setattr(common, "make_anthropic_client",
                        lambda: _client_returning("7"))
    rematch_with_ocr.rematch("src", only_guid=None, dry_run=False)
    out = json.loads((env / "a.json").read_text("utf-8"))
    assert out["youtubeUrl"].endswith("v=full1")
    assert out["number"] == 7


@responses.activate
def test_rematch_no_ocr_match_keeps_original(env, monkeypatch):
    _ep(env, "a.json", {
        "guid": "g1", "title": "Episode 7 invité X",
        "youtubeUrl": "https://www.youtube.com/watch?v=short",
        "youtubeDuration": 5 * 60, "audioDuration": 60 * 60, "number": 7,
    })
    videos = [
        {"id": "full1", "title": "Episode 7 invité X", "duration": 60 * 60},
    ]
    monkeypatch.setattr(rematch_with_ocr, "_fetch_channel_videos", lambda c: videos)
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/full1/maxresdefault.jpg",
        body=big, status=200,
    )
    import common
    # OCR renvoie 99 ≠ 7 → on garde l'original.
    monkeypatch.setattr(common, "make_anthropic_client",
                        lambda: _client_returning("99"))
    rematch_with_ocr.rematch("src", only_guid=None, dry_run=False)
    out = json.loads((env / "a.json").read_text("utf-8"))
    assert out["youtubeUrl"].endswith("v=short")


def test_rematch_no_candidates_logs_warning(env, monkeypatch):
    _ep(env, "a.json", {
        "guid": "g1", "title": "Episode 7",
        "youtubeUrl": "https://www.youtube.com/watch?v=short",
        "youtubeDuration": 5 * 60, "audioDuration": 60 * 60, "number": 7,
    })
    # Aucune vidéo ≥ 30 min sur la chaîne.
    monkeypatch.setattr(rematch_with_ocr, "_fetch_channel_videos",
                        lambda c: [{"id": "x", "title": "x", "duration": 60}])
    import common
    monkeypatch.setattr(common, "make_anthropic_client", lambda: MagicMock())
    rematch_with_ocr.rematch("src", only_guid=None, dry_run=False)
    out = json.loads((env / "a.json").read_text("utf-8"))
    assert out["youtubeUrl"].endswith("v=short")


# ===== main() ===============================================================
def test_main_calls_rematch(monkeypatch):
    called = {}
    monkeypatch.setattr(
        rematch_with_ocr, "rematch",
        lambda s, g, d: called.setdefault("a", (s, g, d)),
    )
    monkeypatch.setattr(sys, "argv",
                        ["rematch_with_ocr.py", "--source", "src",
                         "--guid", "g1", "--dry-run"])
    rematch_with_ocr.main()
    assert called["a"] == ("src", "g1", True)
