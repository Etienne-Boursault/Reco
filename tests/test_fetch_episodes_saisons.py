"""Saison et numéro posés à la main : le flux RSS ne doit pas les écraser.

Les saisons 1 à 4 ont reçu leur saison et leur numéro le 2026-11-02, d'après
TheTVDB. Le flux Acast ne connaît que la numérotation continue de 1 à 70.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import fetch_episodes
from fetch_episodes import fetch_episodes as run_fetch
from test_fetch_episodes import _make_fake_feed, _write_source


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """Comme dans test_fetch_episodes : dossiers isolés, flux RSS simulé."""
    import common
    sources, episodes = tmp_path / "sources", tmp_path / "episodes"
    sources.mkdir()
    episodes.mkdir()
    monkeypatch.setattr(common, "SOURCES_DIR", sources)
    monkeypatch.setattr(common, "EPISODES_DIR", episodes)
    reponse = SimpleNamespace(text="<rss/>", content=b"<rss/>", raise_for_status=lambda: None)
    monkeypatch.setattr(fetch_episodes.requests, "get", lambda url, **kw: reponse)
    return SimpleNamespace(sources=sources, episodes=episodes, root=tmp_path)


def _existant(isolated_dirs, **champs):
    _write_source(isolated_dirs.sources, "ubm", {"id": "ubm", "rssUrl": "https://x/rss"})
    dossier = isolated_dirs.episodes / "ubm"
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / "ep-025.json"
    chemin.write_text(json.dumps({"sourceId": "ubm", "guid": "g-25", "title": "Ancien",
                                  "transcriptStatus": "auto", **champs}), encoding="utf-8")
    return chemin


def _flux(monkeypatch, titre, numero):
    entree = {"id": "g-25", "title": titre, "itunes_episode": str(numero),
              "enclosures": [{"href": "https://x/25.mp3", "type": "audio/mpeg"}]}
    monkeypatch.setattr(fetch_episodes.feedparser, "parse", lambda url: _make_fake_feed([entree]))


def test_the_feed_number_does_not_replace_a_season_number(isolated_dirs, monkeypatch):
    chemin = _existant(isolated_dirs, season=2, number=10)
    _flux(monkeypatch, "Un Bon Moment avec WOODKID et CYPRIEN", 25)

    run_fetch("ubm")

    episode = json.loads(chemin.read_text(encoding="utf-8"))
    assert (episode["season"], episode["number"]) == (2, 10)
    assert episode["title"] == "Un Bon Moment avec WOODKID et CYPRIEN"


def test_a_season_written_in_the_title_still_wins(isolated_dirs, monkeypatch):
    chemin = _existant(isolated_dirs, season=2, number=10)
    _flux(monkeypatch, "Woodkid (Un Bon Moment, S5-E3)", 25)

    run_fetch("ubm")

    episode = json.loads(chemin.read_text(encoding="utf-8"))
    assert (episode["season"], episode["number"]) == (5, 3)


def test_an_episode_without_season_keeps_the_feed_number(isolated_dirs, monkeypatch):
    chemin = _existant(isolated_dirs, number=24)
    _flux(monkeypatch, "Un Bon Moment Hors Série", 25)

    run_fetch("ubm")

    episode = json.loads(chemin.read_text(encoding="utf-8"))
    assert "season" not in episode and episode["number"] == 25
