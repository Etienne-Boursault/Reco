"""Tests : tools.match_audit.title_similarity."""
from __future__ import annotations

from tools.match_audit.protocols import EpisodeView
from tools.match_audit.title_similarity import (
    TitleSimilarityCheck,
    check_title_similarity,
)
from tools.match_audit.types import MatchSuspicion, Severity


def test_titles_similar_returns_none():
    ep = {"title": "avec HAKIM JEMILI", "youtubeTitle": "Un Bon Moment avec HAKIM JEMILI"}
    assert check_title_similarity(ep) is None


def test_titles_diverge_returns_warning_suspicion():
    """CR L3 — severity=warning DOCUMENTÉE par défaut."""
    ep = {"title": "avec HAKIM JEMILI", "youtubeTitle": "Cooking pasta tonight"}
    res = check_title_similarity(ep)
    assert isinstance(res, MatchSuspicion)
    assert res.kind == "title_drift"
    assert res.severity == Severity.WARNING


def test_missing_youtube_title_returns_none():
    assert check_title_similarity({"title": "x"}) is None


def test_missing_rss_title_returns_none():
    assert check_title_similarity({"youtubeTitle": "x"}) is None


def test_post_normalize_empty_returns_none():
    assert check_title_similarity({"title": "!!!", "youtubeTitle": "@@@"}) is None


def test_threshold_parameter_respected():
    ep = {"title": "abc def", "youtubeTitle": "xyz def"}
    assert check_title_similarity(ep, threshold=0.95) is not None


def test_title_similarity_class():
    view = EpisodeView.from_dict({"guid": "g", "title": "Foo",
                                  "youtubeTitle": "Bar baz quux completely diff"})
    assert view is not None
    res = TitleSimilarityCheck().check(view)
    assert res is not None and res.severity == Severity.WARNING


def test_title_check_class_description_mentions_warning():
    c = TitleSimilarityCheck()
    assert c.severity == Severity.WARNING
    assert c.kind == "title_drift"
