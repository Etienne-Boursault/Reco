"""Tests rss.detector : diff seenGuids vs feed, edge cases."""
from __future__ import annotations

from rss.detector import detect_new_episodes
from rss.parser import ParsedEpisode, ParsedFeed
from rss.state import PollingState


def _make_feed(*guids: str) -> ParsedFeed:
    eps = tuple(
        ParsedEpisode(guid=g, title=f"T{g}", link=f"https://x/{g}", published="")
        for g in guids
    )
    return ParsedFeed(title="X", feed_url="https://x/rss", episodes=eps)


def test_detect_first_run_returns_all_capped_by_limit():
    feed = _make_feed("a", "b", "c", "d", "e", "f")
    state = PollingState(source_id="x")
    new_eps = detect_new_episodes(feed, state, limit=3)
    assert [e.guid for e in new_eps] == ["a", "b", "c"]


def test_detect_skips_already_seen():
    feed = _make_feed("c", "b", "a")
    state = PollingState(source_id="x", seen_guids=("a", "b"))
    new_eps = detect_new_episodes(feed, state)
    assert [e.guid for e in new_eps] == ["c"]


def test_detect_all_seen_returns_empty():
    feed = _make_feed("a", "b")
    state = PollingState(source_id="x", seen_guids=("a", "b"))
    assert detect_new_episodes(feed, state) == []


def test_detect_empty_feed_returns_empty():
    feed = _make_feed()
    state = PollingState(source_id="x")
    assert detect_new_episodes(feed, state) == []


def test_detect_limit_zero_means_no_cap():
    feed = _make_feed("a", "b", "c")
    state = PollingState(source_id="x")
    new_eps = detect_new_episodes(feed, state, limit=0)
    assert len(new_eps) == 3


def test_detect_limit_none_means_no_cap():
    feed = _make_feed("a", "b", "c")
    state = PollingState(source_id="x")
    new_eps = detect_new_episodes(feed, state, limit=None)
    assert len(new_eps) == 3


def test_detect_filters_empty_guid_defensively():
    feed = ParsedFeed(
        title="X", feed_url="",
        episodes=(
            ParsedEpisode(guid="", title="bad", link="", published=""),
            ParsedEpisode(guid="ok", title="ok", link="", published=""),
        ),
    )
    new_eps = detect_new_episodes(feed, PollingState(source_id="x"))
    assert [e.guid for e in new_eps] == ["ok"]
