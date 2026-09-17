"""Tests de `tools/fetch_youtube_episodes.py` — nouveaux épisodes depuis YouTube.

Aucun appel réseau : la liste de la chaîne et le détail d'une vidéo sont des
doubles. Le contenu et l'état vivent dans `tmp_path`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fetch_youtube_episodes as fy

SOURCE = "demo-source"
CHANNEL = "https://www.youtube.com/@Demo"


@pytest.fixture
def content(tmp_path, monkeypatch):
    import common

    monkeypatch.setattr(common, "SOURCES_DIR", tmp_path / "sources")
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path / "output")
    (tmp_path / "sources").mkdir()
    (tmp_path / "episodes" / SOURCE).mkdir(parents=True)
    (tmp_path / "sources" / f"{SOURCE}.json").write_text(json.dumps({
        "id": SOURCE, "youtubeChannel": CHANNEL,
        "youtubeTitleSuffixPatterns": ["un bon moment", "a good time"],
    }), encoding="utf-8")
    return tmp_path


def _episodes(root: Path) -> dict[str, dict]:
    out = {}
    for path in sorted((root / "episodes" / SOURCE).glob("*.json")):
        episode = json.loads(path.read_text(encoding="utf-8"))
        out[episode["guid"]] = episode
    return out


def _add_episode(root: Path, **episode) -> None:
    path = root / "episodes" / SOURCE / f"{episode['guid']}.json"
    path.write_text(json.dumps({"sourceId": SOURCE, "title": "t", **episode}),
                    encoding="utf-8")


def _details(video_id: str, **extra) -> dict:
    return {"id": video_id, "title": "Invité (Un Bon Moment, S6-E1)",
            "description": "  Description.  ", "duration": 4950,
            "release_timestamp": 1790150400, "live_status": "not_live", **extra}


def _run(videos, details=None, **kwargs):
    details = details or {}

    def detailer(video_id):
        found = details.get(video_id, _details(video_id))
        if isinstance(found, Exception):
            raise found
        return found

    return fy.fetch_youtube_episodes(SOURCE, lister=lambda _c, _l: videos,
                                     detailer=detailer, **kwargs)


# ===== création =============================================================
def test_a_new_episode_is_created_from_the_video_alone(content):
    videos = [{"id": "-abcDEF123", "title": "Invité (Un Bon Moment, S6-E1)"}]

    result = _run(videos)

    assert result.created == ["yt--abcDEF123"]
    episode = _episodes(content)["yt--abcDEF123"]
    assert episode == {
        "sourceId": SOURCE, "guid": "yt--abcDEF123",
        "title": "Invité (Un Bon Moment, S6-E1)",
        "youtubeTitle": "Invité (Un Bon Moment, S6-E1)",
        "youtubeUrl": "https://www.youtube.com/watch?v=-abcDEF123",
        "season": 6, "number": 1, "guests": [], "transcriptStatus": "none",
        "date": "2026-09-23", "youtubeDuration": 4950, "description": "Description.",
    }


def test_the_file_name_follows_the_episode_naming(content):
    _run([{"id": "-abcDEF123", "title": "X (Un Bon Moment, S6-E1)"}])
    assert (content / "episodes" / SOURCE / "yt-abcdef123.json").exists()


def test_upload_date_is_used_when_no_timestamp(content):
    videos = [{"id": "vid1", "title": "X (Un Bon Moment, S6-E1)"}]
    details = {"vid1": _details("vid1", release_timestamp=None, timestamp=None,
                                upload_date="20260920")}
    _run(videos, details)
    assert _episodes(content)["yt-vid1"]["date"] == "2026-09-20"


# ===== garde-fous ===========================================================
def test_a_video_already_linked_to_an_episode_is_never_recreated(content):
    _add_episode(content, guid="acast-37", season=5, number=37,
                 youtubeUrl="https://www.youtube.com/watch?v=vid37")
    result = _run([{"id": "vid37", "title": "X (Un Bon Moment, S6-E9)"}])
    assert result.created == []
    assert set(_episodes(content)) == {"acast-37"}


def test_an_acast_episode_without_youtube_url_is_matched_by_season_and_number(content):
    _add_episode(content, guid="acast-38", season=6, number=1)
    result = _run([{"id": "vidX", "title": "X (Un Bon Moment, S6-E1)"}])
    assert result.created == []
    assert set(_episodes(content)) == {"acast-38"}


def test_first_run_catches_up_an_episode_but_stays_silent_on_other_videos(content):
    videos = [{"id": "ep", "title": "X (Un Bon Moment, S6-E1)"},
              {"id": "clip", "title": "Un extrait marrant"}]

    result = _run(videos)

    assert result.first_run is True
    assert result.created == ["yt-ep"]
    assert result.unrecognized == []


def test_an_unrecognized_video_is_reported_once_and_never_processed(content):
    _run([])  # premier passage : l'état existe désormais
    clip = {"id": "clip", "title": "Un Bon Moment, hors-série de Noël"}

    first = _run([clip])
    second = _run([clip])

    assert first.unrecognized == [{"id": "clip", "title": clip["title"]}]
    assert second.unrecognized == []
    assert _episodes(content) == {}


@pytest.mark.parametrize("title", [
    "Invité (Un Bon Moment, hors-série)",       # suffixe, pas de numéro
    "Invité S6-E1",                              # numéro, pas de suffixe
])
def test_both_suffix_and_number_are_required(content, title):
    _run([])
    result = _run([{"id": "v", "title": title}])
    assert result.created == [] and len(result.unrecognized) == 1


def test_an_upcoming_premiere_is_deferred_then_created_once_live(content):
    videos = [{"id": "prem", "title": "X (Un Bon Moment, S6-E1)"}]

    waiting = _run(videos, {"prem": _details("prem", live_status="is_upcoming")})
    assert (waiting.created, waiting.deferred) == ([], ["prem"])
    assert _episodes(content) == {}

    live = _run(videos)
    assert live.created == ["yt-prem"]


def test_an_unreadable_video_is_retried_on_the_next_run(content):
    videos = [{"id": "flaky", "title": "X (Un Bon Moment, S6-E1)"}]

    failed = _run(videos, {"flaky": RuntimeError("Sign in to confirm")})
    assert failed.deferred == ["flaky"]

    retried = _run(videos)
    assert retried.created == ["yt-flaky"]


def test_dry_run_writes_neither_episode_nor_state(content):
    result = _run([{"id": "ep", "title": "X (Un Bon Moment, S6-E1)"}], dry_run=True)
    assert result.created == ["yt-ep"]
    assert _episodes(content) == {}
    assert not fy.state_path(SOURCE).exists()


def test_seen_state_is_bounded(content, monkeypatch):
    monkeypatch.setattr(fy, "_MAX_SEEN", 3)
    _run([])
    _run([{"id": f"clip{i}", "title": "extrait"} for i in range(5)])
    seen = json.loads(fy.state_path(SOURCE).read_text(encoding="utf-8"))["seenVideoIds"]
    assert len(seen) == 3


def test_a_source_without_channel_is_an_error(content):
    (content / "sources" / f"{SOURCE}.json").write_text(json.dumps({"id": SOURCE}),
                                                        encoding="utf-8")
    with pytest.raises(ValueError, match="youtubeChannel"):
        _run([])


def test_titles_are_requested_in_french():
    """Sans `lang=fr`, yt-dlp renvoie des titres traduits en anglais."""
    assert fy._YTDLP_BASE["extractor_args"] == {"youtube": {"lang": ["fr"]}}
