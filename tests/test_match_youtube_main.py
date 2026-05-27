"""Tests de la fonction match_youtube() — pipeline complet, mocks yt-dlp."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import match_youtube
from match_youtube import (
    _apply_video_meta,
    match_youtube as run_match,
)


# ===== _apply_video_meta ==================================================
def test_apply_video_meta_sets_all_fields():
    ep: dict[str, Any] = {}
    video = {"title": "Caballero (Un Bon Moment, S5-E32)", "duration": 4200}
    assert _apply_video_meta(ep, video) is True
    assert ep["youtubeTitle"].startswith("Caballero")
    assert ep["youtubeDuration"] == 4200
    assert ep["season"] == 5
    assert ep["number"] == 32


def test_apply_video_meta_no_change_returns_false():
    ep = {
        "youtubeTitle": "T (S1-E2)",
        "youtubeDuration": 100,
        "season": 1,
        "number": 2,
    }
    video = {"title": "T (S1-E2)", "duration": 100}
    assert _apply_video_meta(ep, video) is False


def test_apply_video_meta_partial_update():
    # Seule la durée diffère.
    ep = {"youtubeTitle": "T", "youtubeDuration": 100}
    video = {"title": "T", "duration": 200}
    assert _apply_video_meta(ep, video) is True
    assert ep["youtubeDuration"] == 200


def test_apply_video_meta_invalid_duration_ignored():
    """Si yt-dlp renvoie une durée non-numérique, on ignore au lieu de crasher."""
    ep = {"youtubeTitle": "T"}
    video = {"title": "T", "duration": "pas un nombre"}
    # Pas d'exception ; pas de mise à jour de duration.
    _apply_video_meta(ep, video)
    assert "youtubeDuration" not in ep


# ===== Fixtures pour match_youtube() complet ==============================
@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Isole SOURCES_DIR / EPISODES_DIR dans un tmp_path."""
    import common
    sources = tmp_path / "sources"
    episodes = tmp_path / "episodes"
    sources.mkdir()
    episodes.mkdir()
    monkeypatch.setattr(common, "SOURCES_DIR", sources)
    monkeypatch.setattr(common, "EPISODES_DIR", episodes)
    return SimpleNamespace(sources=sources, episodes=episodes, root=tmp_path)


def _write_source(sources_dir: Path, source_id: str, data: dict) -> None:
    (sources_dir / f"{source_id}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _write_episode(episodes_dir: Path, source_id: str, name: str, data: dict) -> Path:
    d = episodes_dir / source_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


class _FakeYDL:
    """Faux yt_dlp.YoutubeDL : retourne le `info` qui lui est passé."""

    _info: dict[str, Any] = {}

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=False):
        return self._info


def _install_fake_ydl(monkeypatch, info: dict[str, Any]):
    """Monkeypatche yt_dlp.YoutubeDL pour retourner `info` quel que soit l'appel."""
    fake_module = SimpleNamespace(YoutubeDL=type("YDL", (_FakeYDL,), {"_info": info}))
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)


# ===== match_youtube — erreurs et cas limites =============================
def test_match_youtube_raises_without_channel(isolated_dirs):
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm"})  # pas de youtubeChannel
    with pytest.raises(ValueError, match="youtubeChannel"):
        run_match("ubm", threshold=0.5, force=False, dry_run=False)


def test_match_youtube_no_videos_returns_zero(isolated_dirs, monkeypatch):
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://www.youtube.com/@ubm"})
    _install_fake_ydl(monkeypatch, {"entries": []})
    assert run_match("ubm", threshold=0.5, force=False, dry_run=False) == 0


# ===== match_youtube — matching nominal ===================================
def test_match_youtube_associates_episode_to_video(isolated_dirs, monkeypatch):
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://www.youtube.com/@ubm/videos"})
    ep_path = _write_episode(isolated_dirs.episodes, "ubm", "ep-001.json", {
        "sourceId": "ubm", "guid": "g-1", "title": "avec WALY DIA",
    })
    info = {
        "entries": [
            {"id": "VIDWALY", "title": "Un Bon Moment avec WALY DIA (S5-E1)", "duration": 4200},
            {"id": "VIDAUTRE", "title": "Un Bon Moment avec Kheiron (S5-E2)", "duration": 4500},
        ]
    }
    _install_fake_ydl(monkeypatch, info)
    n = run_match("ubm", threshold=0.5, force=False, dry_run=False)
    assert n == 1
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert ep["youtubeUrl"] == "https://www.youtube.com/watch?v=VIDWALY"
    assert ep["season"] == 5
    assert ep["number"] == 1


def test_match_youtube_filters_short_videos(isolated_dirs, monkeypatch):
    """Une vidéo < 30 min (extrait) ne doit jamais être proposée comme épisode."""
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://www.youtube.com/@ubm"})
    ep_path = _write_episode(isolated_dirs.episodes, "ubm", "ep-001.json", {
        "sourceId": "ubm", "guid": "g-1", "title": "avec WALY DIA",
    })
    info = {
        "entries": [
            # Extrait court (15 min) qui aurait matché si on n'avait pas filtré.
            {"id": "SHORT", "title": "Un Bon Moment avec WALY DIA — EXTRAIT", "duration": 900},
            # Vidéo complète (70 min) avec un titre moins direct.
            {"id": "LONG", "title": "Un Bon Moment avec WALY DIA", "duration": 4200},
        ]
    }
    _install_fake_ydl(monkeypatch, info)
    run_match("ubm", threshold=0.5, force=False, dry_run=False)
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert ep["youtubeUrl"].endswith("=LONG")


def test_match_youtube_dry_run_does_not_write(isolated_dirs, monkeypatch):
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://www.youtube.com/@ubm"})
    ep_path = _write_episode(isolated_dirs.episodes, "ubm", "ep-001.json", {
        "sourceId": "ubm", "guid": "g-1", "title": "avec WALY DIA",
    })
    _install_fake_ydl(monkeypatch, {"entries": [
        {"id": "VID1", "title": "Un Bon Moment avec WALY DIA", "duration": 4200}
    ]})
    n = run_match("ubm", threshold=0.5, force=False, dry_run=True)
    assert n == 0
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert "youtubeUrl" not in ep


def test_match_youtube_threshold_too_high_no_match(isolated_dirs, monkeypatch):
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://www.youtube.com/@ubm"})
    _write_episode(isolated_dirs.episodes, "ubm", "ep-001.json", {
        "sourceId": "ubm", "guid": "g-1", "title": "azerty qsdf wxcv",
    })
    _install_fake_ydl(monkeypatch, {"entries": [
        {"id": "VID1", "title": "Tout autre chose sans rapport", "duration": 4200}
    ]})
    assert run_match("ubm", threshold=0.99, force=False, dry_run=False) == 0


def test_match_youtube_skips_already_linked_without_force(isolated_dirs, monkeypatch):
    """Si youtubeUrl existe déjà et qu'on est pas en --force, on ne le change pas."""
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://www.youtube.com/@ubm"})
    ep_path = _write_episode(isolated_dirs.episodes, "ubm", "ep-001.json", {
        "sourceId": "ubm", "guid": "g-1", "title": "avec WALY DIA",
        "youtubeUrl": "https://www.youtube.com/watch?v=ALREADY",
    })
    _install_fake_ydl(monkeypatch, {"entries": [
        # Cette vidéo "ALREADY" est dans la liste : on doit compléter ses métadonnées.
        {"id": "ALREADY", "title": "Un Bon Moment avec WALY DIA (S5-E1)", "duration": 4200},
        # Autre vidéo qui matcherait mieux : doit être ignorée car déjà lié.
        {"id": "BETTER", "title": "avec WALY DIA exact", "duration": 4200},
    ]})
    run_match("ubm", threshold=0.5, force=False, dry_run=False)
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    # URL conservée.
    assert ep["youtubeUrl"].endswith("=ALREADY")
    # Métadonnées complétées depuis la vidéo correspondante.
    assert ep["youtubeDuration"] == 4200
    assert ep["season"] == 5 and ep["number"] == 1


def test_match_youtube_force_overwrites_existing_link(isolated_dirs, monkeypatch):
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://www.youtube.com/@ubm"})
    ep_path = _write_episode(isolated_dirs.episodes, "ubm", "ep-001.json", {
        "sourceId": "ubm", "guid": "g-1", "title": "avec WALY DIA",
        "youtubeUrl": "https://www.youtube.com/watch?v=OLD",
    })
    _install_fake_ydl(monkeypatch, {"entries": [
        {"id": "NEW", "title": "Un Bon Moment avec WALY DIA", "duration": 4200},
    ]})
    run_match("ubm", threshold=0.5, force=True, dry_run=False)
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    assert ep["youtubeUrl"].endswith("=NEW")


def test_match_youtube_channel_url_without_videos_suffix(isolated_dirs, monkeypatch):
    """L'URL de chaîne sans /videos doit y être complétée — pas de plantage."""
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://www.youtube.com/@ubm/"})
    _install_fake_ydl(monkeypatch, {"entries": []})
    # Doit terminer sans erreur (et 0 écriture car aucune vidéo).
    assert run_match("ubm", threshold=0.5, force=False, dry_run=False) == 0


def test_match_youtube_skips_entries_without_id(isolated_dirs, monkeypatch):
    """Les entries sans id renvoyées par yt-dlp sont ignorées."""
    _write_source(isolated_dirs.sources, "ubm",
                  {"id": "ubm", "youtubeChannel": "https://www.youtube.com/@ubm"})
    _write_episode(isolated_dirs.episodes, "ubm", "ep-001.json", {
        "sourceId": "ubm", "guid": "g-1", "title": "avec WALY",
    })
    _install_fake_ydl(monkeypatch, {"entries": [
        None,
        {"title": "Sans id", "duration": 4200},
        {"id": "OK", "title": "Un Bon Moment avec WALY", "duration": 4200},
    ]})
    n = run_match("ubm", threshold=0.5, force=False, dry_run=False)
    assert n == 1
