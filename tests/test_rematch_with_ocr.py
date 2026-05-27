"""Tests du critère « épisode = extrait à corriger » (tools/rematch_with_ocr.py).

`_episode_is_extract` est la définition métier de ce qu'est un extrait au sens
du pipeline : audio Acast complet (≥30 min) mais lien YT vers une vidéo
courte (<30 min).
"""
from __future__ import annotations

import pytest

from rematch_with_ocr import _episode_is_extract, MIN_FULL_EPISODE_SECONDS


def test_extract_when_yt_short_audio_long():
    """Cas standard : extrait YT 8 min, audio 90 min → est un extrait."""
    ep = {"youtubeDuration": 8 * 60, "audioDuration": 90 * 60}
    assert _episode_is_extract(ep) is True


def test_not_extract_when_yt_full_episode():
    """Audio + vidéo YT toutes deux >30 min → pas un extrait."""
    ep = {"youtubeDuration": 60 * 60, "audioDuration": 90 * 60}
    assert _episode_is_extract(ep) is False


def test_not_extract_when_no_audio():
    """Sans audio (épisode mal-formé), on ne peut pas conclure → pas un extrait."""
    ep = {"youtubeDuration": 8 * 60, "audioDuration": None}
    assert _episode_is_extract(ep) is False


def test_not_extract_when_no_youtube():
    """Sans lien YT, pas un extrait au sens du pipeline."""
    ep = {"youtubeDuration": None, "audioDuration": 90 * 60}
    assert _episode_is_extract(ep) is False


def test_not_extract_when_audio_short():
    """Audio aussi court (vrai mini-épisode) → pas un extrait, c'est un format."""
    ep = {"youtubeDuration": 7 * 60, "audioDuration": 7 * 60}
    assert _episode_is_extract(ep) is False


def test_boundary_exactly_30_minutes_not_extract():
    """À 30 min pile, on ne considère pas un extrait (seuil inclusif côté audio)."""
    ep = {"youtubeDuration": MIN_FULL_EPISODE_SECONDS,
          "audioDuration": MIN_FULL_EPISODE_SECONDS}
    assert _episode_is_extract(ep) is False
