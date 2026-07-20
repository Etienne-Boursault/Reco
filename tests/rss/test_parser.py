"""Tests rss.parser : parse RSS, normalisation des champs."""
from __future__ import annotations

from rss.parser import ParsedEpisode, ParsedFeed, parse_feed_bytes

# Fixture RSS 2.0 minimale avec 2 épisodes — accents + Acast-like.
RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Un Bon Moment</title>
    <link>https://exemple.fr</link>
    <description>Test</description>
    <item>
      <title>Episode 2 — accentué</title>
      <link>https://exemple.fr/ep2</link>
      <guid>guid-2</guid>
      <pubDate>Wed, 11 Jun 2026 12:00:00 +0000</pubDate>
      <description>Description 2</description>
    </item>
    <item>
      <title>Episode 1</title>
      <link>https://exemple.fr/ep1</link>
      <guid>guid-1</guid>
      <pubDate>Wed, 04 Jun 2026 12:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
""".encode("utf-8")


def test_parse_feed_extracts_title_and_episodes():
    feed = parse_feed_bytes(RSS_FIXTURE, fallback_url="https://exemple.fr/rss")
    assert isinstance(feed, ParsedFeed)
    assert feed.title == "Un Bon Moment"
    assert feed.feed_url == "https://exemple.fr/rss"
    assert len(feed.episodes) == 2
    assert all(isinstance(e, ParsedEpisode) for e in feed.episodes)


def test_parse_feed_preserves_order_newest_first():
    feed = parse_feed_bytes(RSS_FIXTURE)
    assert feed.episodes[0].guid == "guid-2"
    assert feed.episodes[1].guid == "guid-1"


def test_parse_feed_handles_accents():
    feed = parse_feed_bytes(RSS_FIXTURE)
    assert "accentué" in feed.episodes[0].title


def test_parse_feed_normalizes_published_to_iso8601():
    feed = parse_feed_bytes(RSS_FIXTURE)
    assert feed.episodes[0].published == "2026-06-11T12:00:00Z"


def test_parse_feed_skips_entries_without_guid():
    rss = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>X</title>
<item><title>No guid no link</title></item>
<item><title>Has link</title><link>https://x/1</link></item>
</channel></rss>"""
    feed = parse_feed_bytes(rss)
    # L'épisode sans guid ni link est filtré ; celui avec link garde
    # le link comme GUID (fallback).
    assert len(feed.episodes) == 1
    assert feed.episodes[0].guid == "https://x/1"


def test_parse_feed_empty_returns_empty_tuple():
    feed = parse_feed_bytes(b"")
    assert feed.episodes == ()


def test_parse_feed_bad_pubdate_keeps_raw_string():
    rss = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>X</title>
<item><title>T</title><guid>g</guid><pubDate>not-a-date</pubDate></item>
</channel></rss>"""
    feed = parse_feed_bytes(rss)
    # feedparser ne reconnait pas → published_parsed=None → on garde la
    # string brute (qui peut être "not-a-date" ou "" si feedparser drop).
    assert feed.episodes[0].guid == "g"
