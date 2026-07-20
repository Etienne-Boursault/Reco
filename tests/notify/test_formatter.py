"""Tests notify.formatter : troncature, échappement, payloads multi-canal."""
from __future__ import annotations

from notify.formatter import (
    DISCORD_EMBED_TITLE_LIMIT,
    NewEpisodeMessage,
    build_discord_embed,
    build_plain_text,
    build_slack_blocks,
    escape_discord_markdown,
    truncate,
)


def test_truncate_short_text_unchanged():
    assert truncate("hello", 10) == "hello"


def test_truncate_long_text_adds_ellipsis():
    out = truncate("hello world", 8)
    assert out.endswith("…")
    assert len(out) <= 8


def test_truncate_zero_limit_returns_empty():
    assert truncate("x", 0) == ""


def test_truncate_limit_smaller_than_ellipsis():
    assert truncate("hello", 1) == "h"


def test_escape_discord_markdown_handles_specials():
    assert escape_discord_markdown("a*b_c") == "a\\*b\\_c"


def test_escape_discord_markdown_no_specials():
    assert escape_discord_markdown("hello") == "hello"


def _msg(**overrides) -> NewEpisodeMessage:
    base = dict(
        feed_title="Un Bon Moment",
        episode_title="Episode 42",
        episode_url="https://exemple.fr/42",
        published_at="2026-06-11T12:00:00Z",
        source_id="ubm",
    )
    base.update(overrides)
    return NewEpisodeMessage(**base)


def test_build_discord_embed_basic_structure():
    payload = build_discord_embed(_msg())
    assert "embeds" in payload
    embed = payload["embeds"][0]
    assert "Un Bon Moment" in embed["title"]
    assert embed["description"] == "Episode 42"
    assert embed["url"] == "https://exemple.fr/42"
    assert embed["timestamp"] == "2026-06-11T12:00:00Z"
    assert embed["color"] == 0x5EEAD4
    assert embed["footer"]["text"] == "Reco poll RSS"


def test_build_discord_embed_truncates_long_title():
    long_feed = "x" * 500
    payload = build_discord_embed(_msg(feed_title=long_feed))
    assert len(payload["embeds"][0]["title"]) <= DISCORD_EMBED_TITLE_LIMIT


def test_build_discord_embed_escapes_markdown_in_feed_title():
    payload = build_discord_embed(_msg(feed_title="Bold*Title"))
    assert "\\*" in payload["embeds"][0]["title"]


def test_build_discord_embed_without_url():
    payload = build_discord_embed(_msg(episode_url=""))
    assert "url" not in payload["embeds"][0]


def test_build_discord_embed_without_published():
    payload = build_discord_embed(_msg(published_at=""))
    assert "timestamp" not in payload["embeds"][0]


def test_build_slack_blocks_structure():
    payload = build_slack_blocks(_msg())
    assert payload["blocks"][0]["type"] == "header"
    assert payload["blocks"][1]["type"] == "section"
    assert "Episode 42" in payload["blocks"][1]["text"]["text"]
    assert "exemple.fr/42" in payload["blocks"][1]["text"]["text"]


def test_build_slack_blocks_without_url():
    payload = build_slack_blocks(_msg(episode_url=""))
    body = payload["blocks"][1]["text"]["text"]
    assert "Écouter" not in body


def test_build_slack_blocks_without_published():
    payload = build_slack_blocks(_msg(published_at=""))
    body = payload["blocks"][1]["text"]["text"]
    assert "Publié" not in body


def test_build_plain_text_contains_key_fields():
    text = build_plain_text(_msg())
    assert "Un Bon Moment" in text
    assert "Episode 42" in text
    assert "https://exemple.fr/42" in text
    assert "2026-06-11" in text


def test_build_plain_text_without_optional_fields():
    text = build_plain_text(_msg(episode_url="", published_at=""))
    assert "Lien" not in text
    assert "Publié" not in text
