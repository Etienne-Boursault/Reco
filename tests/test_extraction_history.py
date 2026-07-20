"""Tests pour `tools/extraction_history.py` — couverture 100%."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Permet d'importer le module depuis tools/ comme le font les autres tests.
_TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from extraction_history import (  # noqa: E402
    ASSUMED,
    ExtractionEntry,
    derive_extractors,
    from_dict,
    merge_history,
    pick_display_state,
    pick_latest_yt,
    to_dict,
)


def _entry(
    at="2026-06-01T10:00:00",
    transcriptModel="large-v3",
    transcriptSource="acast",
    llmProvider="anthropic",
    llmModel="claude-haiku-4-5",
    worker="main-cpu",
    timestamp_at_extraction="00:42:00",
) -> ExtractionEntry:
    return ExtractionEntry(
        at=at,
        transcriptModel=transcriptModel,
        transcriptSource=transcriptSource,
        llmProvider=llmProvider,
        llmModel=llmModel,
        worker=worker,
        timestamp_at_extraction=timestamp_at_extraction,
    )


# ===== signature / equality ===============================================
def test_entry_signature_equality():
    a = _entry()
    b = _entry(at="2026-06-02T11:00:00", worker="portable-gpu",
               timestamp_at_extraction="00:43:00")
    # at/worker/timestamp_at_extraction n'entrent PAS dans la signature.
    assert a.signature() == b.signature()


def test_entry_signature_includes_all_4_axes():
    base = _entry()
    assert base.signature() != _entry(transcriptModel="small").signature()
    assert base.signature() != _entry(transcriptSource="youtube").signature()
    assert base.signature() != _entry(llmProvider="openai").signature()
    assert base.signature() != _entry(llmModel="gpt-4o-mini").signature()


# ===== to_dict / from_dict ================================================
def test_to_dict_roundtrip():
    e = _entry()
    d = to_dict(e)
    assert d["at"] == "2026-06-01T10:00:00"
    assert d["transcriptSource"] == "acast"
    assert from_dict(d) == e


def test_from_dict_fills_missing_with_assumed():
    e = from_dict({"at": "2026-01-01T00:00:00"})
    assert e.transcriptModel == ASSUMED
    assert e.llmModel == ASSUMED
    assert e.worker == ASSUMED
    assert e.transcriptSource == "acast"
    assert e.llmProvider == "anthropic"
    assert e.timestamp_at_extraction == "00:00:00"


# ===== merge_history ======================================================
def test_merge_history_adds_new_entry():
    a = _entry(at="2026-06-01T10:00:00")
    b = _entry(at="2026-06-02T10:00:00", llmProvider="openai",
               llmModel="gpt-4o-mini")
    merged = merge_history([a], b)
    assert len(merged) == 2
    assert merged[0] is a
    assert merged[1] is b


def test_merge_history_dedupes_by_signature_and_updates_at():
    a = _entry(at="2026-06-01T10:00:00", timestamp_at_extraction="00:10:00")
    b = _entry(at="2026-06-02T10:00:00", timestamp_at_extraction="00:11:00",
               worker="portable-gpu")
    merged = merge_history([a], b)
    assert len(merged) == 1
    assert merged[0].at == "2026-06-02T10:00:00"
    assert merged[0].timestamp_at_extraction == "00:11:00"
    assert merged[0].worker == "portable-gpu"


def test_merge_history_dedupes_keeps_latest_timestamp_at_extraction():
    """Si nouvel `at` plus récent → on prend son timestamp_at_extraction."""
    old = _entry(at="2026-06-01T10:00:00", timestamp_at_extraction="00:10:00")
    new = _entry(at="2026-06-05T10:00:00", timestamp_at_extraction="00:12:34")
    merged = merge_history([old], new)
    assert merged[0].timestamp_at_extraction == "00:12:34"


def test_merge_history_dedupe_keeps_old_if_new_is_older():
    new = _entry(at="2026-06-05T10:00:00", timestamp_at_extraction="00:12:34")
    older = _entry(at="2026-06-01T10:00:00", timestamp_at_extraction="00:10:00")
    merged = merge_history([new], older)
    assert len(merged) == 1
    assert merged[0].at == "2026-06-05T10:00:00"
    assert merged[0].timestamp_at_extraction == "00:12:34"


def test_merge_history_equal_at_updates_to_new_payload():
    """Égalité d'`at` (granularité seconde) → la nouvelle entrée gagne."""
    old = _entry(at="2026-06-05T10:00:00", timestamp_at_extraction="00:10:00",
                 worker="(assumed)")
    new = _entry(at="2026-06-05T10:00:00", timestamp_at_extraction="00:12:34",
                 worker="portable-gpu")
    merged = merge_history([old], new)
    assert len(merged) == 1
    assert merged[0].timestamp_at_extraction == "00:12:34"
    assert merged[0].worker == "portable-gpu"


def test_merge_history_preserves_chronological_order():
    a = _entry(at="2026-06-03T10:00:00", llmProvider="anthropic")
    b = _entry(at="2026-06-01T10:00:00", llmProvider="openai",
               llmModel="gpt-4o-mini")
    c = _entry(at="2026-06-02T10:00:00", transcriptSource="youtube")
    merged = merge_history(merge_history([a], b), c)
    ats = [e.at for e in merged]
    assert ats == sorted(ats)


# ===== derive_extractors ==================================================
def test_derive_extractors_dedupes_providers():
    h = [
        _entry(llmProvider="anthropic", llmModel="haiku"),
        _entry(at="2026-06-02T10:00:00",
               llmProvider="anthropic", llmModel="sonnet"),
        _entry(at="2026-06-03T10:00:00",
               llmProvider="openai", llmModel="gpt-4o-mini"),
    ]
    assert derive_extractors(h) == ["anthropic", "openai"]


def test_derive_extractors_empty():
    assert derive_extractors([]) == []


# ===== pick_latest_yt =====================================================
def test_pick_latest_yt_returns_none_if_only_acast():
    h = [_entry(transcriptSource="acast")]
    assert pick_latest_yt(h) is None


def test_pick_latest_yt_returns_most_recent_yt_when_multiple():
    h = [
        _entry(at="2026-06-01T10:00:00", transcriptSource="youtube",
               timestamp_at_extraction="00:10:00"),
        _entry(at="2026-06-05T10:00:00", transcriptSource="youtube",
               timestamp_at_extraction="00:42:42",
               llmProvider="openai", llmModel="gpt-4o-mini"),
        _entry(at="2026-06-06T10:00:00", transcriptSource="acast",
               timestamp_at_extraction="00:99:99"),
    ]
    latest = pick_latest_yt(h)
    assert latest is not None
    assert latest.timestamp_at_extraction == "00:42:42"


# ===== pick_display_state =================================================
def test_pick_display_state_prefers_yt_over_more_recent_acast():
    h = [
        _entry(at="2026-06-01T10:00:00", transcriptSource="youtube",
               timestamp_at_extraction="00:42:42"),
        _entry(at="2026-06-05T10:00:00", transcriptSource="acast",
               timestamp_at_extraction="00:99:99",
               llmProvider="openai", llmModel="gpt-4o-mini"),
    ]
    state = pick_display_state(h)
    assert state == {"timestamp": "00:42:42", "transcriptSource": "youtube"}


def test_pick_display_state_falls_back_to_acast():
    h = [
        _entry(at="2026-06-01T10:00:00", transcriptSource="acast",
               timestamp_at_extraction="00:10:00"),
        _entry(at="2026-06-05T10:00:00", transcriptSource="acast",
               timestamp_at_extraction="00:42:42",
               llmProvider="openai", llmModel="gpt-4o-mini"),
    ]
    state = pick_display_state(h)
    assert state == {"timestamp": "00:42:42", "transcriptSource": "acast"}


def test_pick_display_state_empty_history():
    state = pick_display_state([])
    assert state == {"timestamp": "00:00:00", "transcriptSource": "acast"}
