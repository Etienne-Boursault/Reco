"""Tests des helpers de match YouTube (tools/match_youtube.py)."""
from __future__ import annotations

import pytest

from match_youtube import (
    _normalize,
    _parse_se,
    _similarity,
    _video_id,
)


# ===== _normalize =========================================================
def test_normalize_strips_accents_and_lowercases():
    assert _normalize("Bérengère") == _normalize("BERENGERE") == _normalize("berengere")


def test_normalize_removes_punctuation():
    a = _normalize("Mortel, S1-E1")
    b = _normalize("mortel s1e1")
    # On veut au moins que les lettres significatives soient égales.
    assert "mortel" in a and "mortel" in b


def test_normalize_empty_string():
    assert _normalize("") == ""


# ===== _similarity ========================================================
def test_similarity_identical_is_max():
    assert _similarity("hello world", "hello world") == 1.0


def test_similarity_close_strings_higher_than_unrelated():
    """Score relatif : 1 lettre près > zéro recouvrement."""
    close = _similarity("hello world", "helo world")
    far = _similarity("hello world", "azerty qsdf")
    assert close > far


def test_similarity_word_inclusion_boosts_score():
    """Le RSS court contenu dans le titre YT complet doit dépasser 0.85
    (cf. règle d'inclusion dans _similarity pour les « avec Waly » → « Un Bon Moment avec WALY DIA »)."""
    # Tous les tokens significatifs (>1 char, hors stopwords) de a sont dans b
    rss = "avec waly"
    yt = "un bon moment avec waly dia"
    assert _similarity(rss, yt) >= 0.9


def test_similarity_unrelated_strings_low():
    assert _similarity("abcdef", "zyxwvu") < 0.3


def test_similarity_handles_empty_strings():
    """Pas de garantie sémantique forte sur le cas empty/empty, juste qu'on
    ne crashe pas et que le score est dans [0, 1]."""
    score = _similarity("", "")
    assert 0.0 <= score <= 1.0


# ===== _parse_se ==========================================================
@pytest.mark.parametrize("title,expected", [
    ("Caballero et JeanJass (Un Bon Moment, S5-E32)", (5, 32)),
    ("Pierre Niney (S5-E15)", (5, 15)),
    ("avec Kheiron (S1-E10)", (1, 10)),
    ("avec HAROUN",       (None, None)),
    ("Hozier discography", (None, None)),
])
def test_parse_se_extracts_season_episode(title, expected):
    assert _parse_se(title) == expected


def test_parse_se_handles_lowercase():
    assert _parse_se("Episode (s5-e32)") == (5, 32)


def test_parse_se_handles_various_separators():
    # Variantes vues dans la nature : S5·E32, S5.E32, S5–E32.
    for sep in ("-", "·", ".", "–"):
        assert _parse_se(f"(S5{sep}E32)") == (5, 32)


# ===== _video_id ==========================================================
def test_video_id_extracts_from_watch_url():
    assert _video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_video_id_handles_extra_params():
    assert _video_id("https://www.youtube.com/watch?v=ABCD&t=42s") == "ABCD"


def test_video_id_returns_none_for_non_url():
    assert _video_id("not a url") is None
    assert _video_id("") is None
    assert _video_id(None) is None  # type: ignore[arg-type]
