"""Tests : tools.match_audit.duration_check."""
from __future__ import annotations

import pytest

from tools.match_audit.duration_check import DurationCheck, check_duration
from tools.match_audit.protocols import EpisodeView
from tools.match_audit.types import MatchSuspicion, Severity


def _ep(audio: int | None = None, yt: int | None = None) -> dict:
    d: dict = {"guid": "g1"}
    if audio is not None:
        d["audioDuration"] = audio
    if yt is not None:
        d["youtubeDuration"] = yt
    return d


# ---------------------------------------------------------------------------
# Function form (rétrocompat)
# ---------------------------------------------------------------------------


def test_durations_match_returns_none():
    assert check_duration(_ep(3600, 3700)) is None


def test_durations_diverge_returns_suspicion_with_exact_detail():
    """CR senior M1 — assertion spécifique au pourcentage."""
    result = check_duration(_ep(3600, 5400))
    assert isinstance(result, MatchSuspicion)
    assert result.kind == "duration_mismatch"
    assert result.severity == Severity.ERROR
    assert "50.0%" in result.detail
    assert "Acast=3600s" in result.detail
    assert "YT=5400s" in result.detail


def test_durations_audio_missing_returns_none():
    assert check_duration(_ep(None, 3600)) is None


def test_durations_youtube_missing_returns_none():
    assert check_duration(_ep(3600, None)) is None


def test_durations_both_missing_returns_none():
    assert check_duration(_ep()) is None


def test_tolerance_parameter_respected():
    assert check_duration(_ep(1000, 1060), tolerance=0.05) is not None
    assert check_duration(_ep(1000, 1060), tolerance=0.10) is None


def test_durations_zero_audio_returns_none():
    """Garde-fou : ne divise pas par zéro."""
    assert check_duration(_ep(0, 100)) is None


def test_durations_negative_audio_returns_none():
    """Bord : audio < 0 → no-op (les durées sont positives)."""
    assert check_duration(_ep(-10, 100)) is None


def test_durations_invalid_payload_returns_none():
    """Si l'argument n'est même pas un dict, on retourne None proprement."""
    assert check_duration("not-a-dict") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Class form (Protocol MatchCheck)
# ---------------------------------------------------------------------------


def test_duration_check_class_kind_and_severity():
    c = DurationCheck()
    assert c.kind == "duration_mismatch"
    assert c.severity == Severity.ERROR
    assert "audioDuration" in c.description


def test_duration_check_class_accepts_episode_view():
    view = EpisodeView.from_dict({"guid": "g", "audioDuration": 1000,
                                  "youtubeDuration": 2000})
    assert view is not None
    r = DurationCheck().check(view)
    assert r is not None and r.kind == "duration_mismatch"


def test_duration_check_class_custom_tolerance():
    view = EpisodeView.from_dict({"guid": "g", "audioDuration": 1000,
                                  "youtubeDuration": 1060})
    assert view is not None
    assert DurationCheck(tolerance=0.10).check(view) is None
    assert DurationCheck(tolerance=0.05).check(view) is not None


def test_duration_check_is_immutable():
    """frozen dataclass."""
    c = DurationCheck()
    with pytest.raises(Exception):
        c.tolerance = 0.99  # type: ignore[misc]
