"""Tests : tools.match_audit.intro_text_similarity."""
from __future__ import annotations

import pytest

from tools.match_audit.intro_text_similarity import (
    IntroTextSimilarityCheck,
    check_intro_similarity,
)
from tools.match_audit.protocols import EpisodeView
from tools.match_audit.types import MatchSuspicion, Severity


def _ep() -> dict:
    return {"guid": "g1", "sourceId": "src"}


_ACAST = "Bonjour et bienvenue dans Un Bon Moment avec Kyan Khojandi et Navo."
_YT_OK = "Bonjour et bienvenue dans Un Bon Moment avec Kyan et Navo, on est ravis."
_YT_DIFF = "This is a completely unrelated transcript about cooking pasta in Rome."


class _DictRepo:
    """TranscriptRepo de test : sert depuis deux dicts."""

    def __init__(self, acast: dict[str, str | None], yt: dict[str, str | None]):
        self._a = acast
        self._y = yt

    def get(self, guid: str, kind):
        return self._a.get(guid) if kind == "acast" else self._y.get(guid)


# ---------------------------------------------------------------------------
# Legacy callable API
# ---------------------------------------------------------------------------


def test_similar_intros_returns_none():
    res = check_intro_similarity(
        _ep(),
        acast_transcript_provider=lambda g: _ACAST,
        yt_transcript_provider=lambda g: _YT_OK,
    )
    assert res is None


def test_different_intros_returns_error_suspicion():
    res = check_intro_similarity(
        _ep(),
        acast_transcript_provider=lambda g: _ACAST,
        yt_transcript_provider=lambda g: _YT_DIFF,
    )
    assert isinstance(res, MatchSuspicion)
    assert res.kind == "intro_mismatch"
    assert res.severity == Severity.ERROR


def test_missing_acast_returns_none():
    res = check_intro_similarity(
        _ep(),
        acast_transcript_provider=lambda g: None,
        yt_transcript_provider=lambda g: _YT_OK,
    )
    assert res is None


def test_missing_yt_returns_none():
    res = check_intro_similarity(
        _ep(),
        acast_transcript_provider=lambda g: _ACAST,
        yt_transcript_provider=lambda g: None,
    )
    assert res is None


def test_threshold_parameter_respected():
    res = check_intro_similarity(
        _ep(),
        acast_transcript_provider=lambda g: _ACAST,
        yt_transcript_provider=lambda g: _YT_OK,
        threshold=0.99,
    )
    assert res is not None


def test_post_normalize_empty_returns_none():
    res = check_intro_similarity(
        _ep(),
        acast_transcript_provider=lambda g: "!!!",
        yt_transcript_provider=lambda g: "@@@",
    )
    assert res is None


def test_empty_transcripts_returns_none():
    res = check_intro_similarity(
        _ep(),
        acast_transcript_provider=lambda g: "",
        yt_transcript_provider=lambda g: "",
    )
    assert res is None


def test_missing_repo_and_providers_raises():
    """Si ni transcript_repo ni les providers ne sont fournis → ValueError."""
    with pytest.raises(ValueError):
        check_intro_similarity(_ep())


# ---------------------------------------------------------------------------
# New API : TranscriptRepo + IntroTextSimilarityCheck
# ---------------------------------------------------------------------------


def test_transcript_repo_path_similar():
    repo = _DictRepo({"g1": _ACAST}, {"g1": _YT_OK})
    res = check_intro_similarity(_ep(), transcript_repo=repo)
    assert res is None


def test_transcript_repo_path_diverge_flags():
    repo = _DictRepo({"g1": _ACAST}, {"g1": _YT_DIFF})
    res = check_intro_similarity(_ep(), transcript_repo=repo)
    assert res is not None and res.kind == "intro_mismatch"


def test_intro_class_uses_view_and_repo():
    repo = _DictRepo({"g1": _ACAST}, {"g1": _YT_DIFF})
    check = IntroTextSimilarityCheck(transcript_repo=repo)
    view = EpisodeView.from_dict({"guid": "g1"})
    assert view is not None
    res = check.check(view)
    assert res is not None and res.severity == Severity.ERROR


def test_intro_class_kind_severity_description():
    repo = _DictRepo({}, {})
    check = IntroTextSimilarityCheck(transcript_repo=repo)
    assert check.kind == "intro_mismatch"
    assert check.severity == Severity.ERROR
    assert "transcript" in check.description.lower()


def test_intro_check_takes_max_of_intro_and_mid_window():
    """CR senior H8 — on prend le MAX entre intro et fenêtre milieu :
    si le milieu est très proche, on ne flag pas (vrai-positif réduit
    sur jingle générique), si les deux divergent, on flag.
    """
    # Cas 1 : intro identique mais milieu identique → pas de flag.
    common_jingle = "musique intro " * 50
    common_mid = "x" * 6000  # même chose à 5000+
    repo_same = _DictRepo({"g1": common_jingle + common_mid},
                          {"g1": common_jingle + common_mid})
    assert check_intro_similarity(_ep(), transcript_repo=repo_same) is None

    # Cas 2 : tout diffère → flag.
    repo_diff = _DictRepo(
        {"g1": "bonjour tout le monde " * 500},
        {"g1": "cooking pasta with garlic " * 500},
    )
    res = check_intro_similarity(_ep(), transcript_repo=repo_diff)
    assert res is not None
    assert res.kind == "intro_mismatch"


def test_legacy_intro_embedding_check_module_reexports():
    """Le nom historique reste importable (alias rétrocompat)."""
    from tools.match_audit import intro_embedding_check as legacy
    from tools.match_audit.intro_text_similarity import (
        IntroTextSimilarityCheck as Canon,
        check_intro_similarity as canon_fn,
    )
    assert legacy.IntroTextSimilarityCheck is Canon
    assert legacy.check_intro_similarity is canon_fn


def test_intro_check_short_transcript_no_mid_window():
    """Si les transcripts sont < 5000 chars, la fenêtre milieu retourne ""
    et seule l'intro compte (pas de NPE)."""
    repo = _DictRepo({"g1": "court a"}, {"g1": "court b"})
    # Peu de matière → similarité dépend du contenu, mais pas de crash.
    _ = check_intro_similarity(_ep(), transcript_repo=repo)
