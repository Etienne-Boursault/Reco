"""Tests pour `tools/ocr_thumbnails.py`."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import responses

import ocr_thumbnails


# ===== _video_id ============================================================
@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=ABC123_-x", "ABC123_-x"),
    ("https://youtu.be/XYZ", None),  # pas le format ?v=
    ("https://www.youtube.com/watch?foo=bar&v=DEF456", "DEF456"),
    ("", None),
    (None, None),
])
def test_video_id(url, expected):
    assert ocr_thumbnails._video_id(url) == expected


# ===== _download_thumb ======================================================
@responses.activate
def test_download_thumb_maxres_ok():
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/abc/maxresdefault.jpg",
        body=big, status=200, content_type="image/jpeg",
    )
    assert ocr_thumbnails._download_thumb("abc") == big


@responses.activate
def test_download_thumb_falls_back_to_hq():
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/abc/maxresdefault.jpg",
        body=b"tiny", status=200,
    )
    big = b"\xff\xd8" + b"y" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/abc/hqdefault.jpg",
        body=big, status=200,
    )
    assert ocr_thumbnails._download_thumb("abc") == big


@responses.activate
def test_download_thumb_all_fail():
    for q in ("maxresdefault", "hqdefault"):
        responses.add(
            responses.GET, f"https://i.ytimg.com/vi/abc/{q}.jpg",
            status=404,
        )
    assert ocr_thumbnails._download_thumb("abc") is None


# ===== _read_number =========================================================
def _client_returning(text: str):
    """Fabrique un MagicMock qui simule client.messages.create."""
    block = SimpleNamespace(type="text", text=text)
    msg = SimpleNamespace(content=[block])
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def test_read_number_extracts_int():
    client = _client_returning("42")
    assert ocr_thumbnails._read_number(client, b"\xff\xd8data") == 42


def test_read_number_no_digit_returns_none():
    client = _client_returning("NONE")
    assert ocr_thumbnails._read_number(client, b"\xff\xd8data") is None


def test_read_number_ignores_non_text_blocks():
    """Les blocs sans type='text' sont ignorés."""
    text_block = SimpleNamespace(type="text", text="EP 7")
    img_block = SimpleNamespace(type="image", text="ignored 999")
    msg = SimpleNamespace(content=[img_block, text_block])
    client = MagicMock()
    client.messages.create.return_value = msg
    assert ocr_thumbnails._read_number(client, b"data") == 7


# ===== run() ================================================================
@pytest.fixture
def ep_env(tmp_path, monkeypatch):
    eps_dir = tmp_path / "eps"
    eps_dir.mkdir()
    monkeypatch.setattr(ocr_thumbnails, "list_episode_files",
                        lambda s: sorted(eps_dir.glob("*.json")))
    return eps_dir


def _ep(d, name, data):
    p = d / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


@responses.activate
def test_run_writes_number(ep_env, monkeypatch):
    _ep(ep_env, "a.json", {"guid": "g1", "title": "E",
                            "youtubeUrl": "https://www.youtube.com/watch?v=abc"})
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/abc/maxresdefault.jpg",
        body=big, status=200,
    )
    # Stub make_anthropic_client (importé paresseusement dans run()).
    import common
    monkeypatch.setattr(common, "make_anthropic_client",
                        lambda: _client_returning("42"))
    written = ocr_thumbnails.run("src", dry_run=False)
    assert written == 1
    out = json.loads((ep_env / "a.json").read_text("utf-8"))
    assert out["number"] == 42


def test_run_skip_if_number_already_set(ep_env, monkeypatch):
    _ep(ep_env, "a.json", {"guid": "g", "title": "E", "number": 5,
                            "youtubeUrl": "https://www.youtube.com/watch?v=abc"})
    import extract_recos
    monkeypatch.setattr(extract_recos, "_make_client", lambda: MagicMock())
    assert ocr_thumbnails.run("src", dry_run=False) == 0


def test_run_skip_if_no_youtube_url(ep_env, monkeypatch):
    _ep(ep_env, "a.json", {"guid": "g", "title": "E"})
    import extract_recos
    monkeypatch.setattr(extract_recos, "_make_client", lambda: MagicMock())
    assert ocr_thumbnails.run("src", dry_run=False) == 0


def test_run_skip_if_video_id_unparsable(ep_env, monkeypatch):
    _ep(ep_env, "a.json", {"guid": "g", "title": "E",
                            "youtubeUrl": "https://youtu.be/xyz"})
    import extract_recos
    monkeypatch.setattr(extract_recos, "_make_client", lambda: MagicMock())
    assert ocr_thumbnails.run("src", dry_run=False) == 0


@responses.activate
def test_run_thumb_missing_warns_continues(ep_env, monkeypatch):
    _ep(ep_env, "a.json", {"guid": "g", "title": "E",
                            "youtubeUrl": "https://www.youtube.com/watch?v=abc"})
    for q in ("maxresdefault", "hqdefault"):
        responses.add(
            responses.GET, f"https://i.ytimg.com/vi/abc/{q}.jpg",
            status=404,
        )
    import extract_recos
    monkeypatch.setattr(extract_recos, "_make_client", lambda: MagicMock())
    assert ocr_thumbnails.run("src", dry_run=False) == 0


@responses.activate
def test_run_dry_run_does_not_call_client(ep_env, monkeypatch):
    _ep(ep_env, "a.json", {"guid": "g", "title": "E",
                            "youtubeUrl": "https://www.youtube.com/watch?v=abc"})
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/abc/maxresdefault.jpg",
        body=big, status=200,
    )
    # _make_client ne doit PAS être appelé en dry-run.
    import extract_recos
    sentinel = MagicMock(side_effect=AssertionError("ne doit pas être appelé"))
    monkeypatch.setattr(extract_recos, "_make_client", sentinel)
    assert ocr_thumbnails.run("src", dry_run=True) == 0
    sentinel.assert_not_called()


@responses.activate
def test_run_no_number_in_ocr(ep_env, monkeypatch):
    _ep(ep_env, "a.json", {"guid": "g", "title": "E",
                            "youtubeUrl": "https://www.youtube.com/watch?v=abc"})
    big = b"\xff\xd8" + b"x" * 3000
    responses.add(
        responses.GET, "https://i.ytimg.com/vi/abc/maxresdefault.jpg",
        body=big, status=200,
    )
    import common
    monkeypatch.setattr(common, "make_anthropic_client",
                        lambda: _client_returning("NONE"))
    assert ocr_thumbnails.run("src", dry_run=False) == 0


# ===== main() ===============================================================
def test_main_calls_run(monkeypatch):
    called = {}
    monkeypatch.setattr(ocr_thumbnails, "run",
                        lambda s, d: called.setdefault("args", (s, d)) or 0)
    monkeypatch.setattr(sys, "argv",
                        ["ocr_thumbnails.py", "--source", "src", "--dry-run"])
    ocr_thumbnails.main()
    assert called["args"] == ("src", True)
