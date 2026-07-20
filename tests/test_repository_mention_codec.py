"""Tests de `tools.repository.serialization.mention_codec` — purs (zéro IO).

Couverture 100% requise. TDD strict.
"""
from __future__ import annotations

import pytest

from domain.mention import (
    ExtractionHistoryEntry,
    Mention,
    MentionKind,
    MentionStatus,
    SourceRef,
    TranscriptSource,
)
from repository.serialization.mention_codec import (
    extraction_history_entry_from_dict,
    extraction_history_entry_to_dict,
    mention_from_dict,
    mention_to_dict,
    source_ref_from_dict,
    source_ref_to_dict,
)


# ---------------------------------------------------------------------------
# SourceRef
# ---------------------------------------------------------------------------


def test_source_ref_round_trip_minimal():
    sr = SourceRef(source_id="un-bon-moment")
    assert source_ref_from_dict(source_ref_to_dict(sr)) == sr


def test_source_ref_round_trip_full():
    sr = SourceRef(
        source_id="un-bon-moment",
        episode_guid="ep-001",
        timestamp="01:02:03",
        transcript_source=TranscriptSource.YOUTUBE,
    )
    assert source_ref_from_dict(source_ref_to_dict(sr)) == sr


def test_source_ref_to_dict_omits_none():
    sr = SourceRef(source_id="x")
    d = source_ref_to_dict(sr)
    assert d == {"sourceId": "x"}


def test_source_ref_to_dict_uses_camelcase():
    sr = SourceRef(
        source_id="x",
        episode_guid="g",
        timestamp="00:00:01",
        transcript_source=TranscriptSource.ACAST,
    )
    d = source_ref_to_dict(sr)
    assert d == {
        "sourceId": "x",
        "episodeGuid": "g",
        "timestamp": "00:00:01",
        "transcriptSource": "acast",
    }


def test_source_ref_from_dict_missing_source_id_raises():
    with pytest.raises((KeyError, ValueError)):
        source_ref_from_dict({})


# ---------------------------------------------------------------------------
# ExtractionHistoryEntry
# ---------------------------------------------------------------------------


def test_extraction_history_entry_round_trip_minimal():
    e = ExtractionHistoryEntry(
        transcript_model=None,
        transcript_source=None,
        llm_provider="anthropic",
        llm_model="claude-3",
        worker=None,
        at="2026-06-10T14:00:00Z",
    )
    assert extraction_history_entry_from_dict(
        extraction_history_entry_to_dict(e)
    ) == e


def test_extraction_history_entry_round_trip_full():
    e = ExtractionHistoryEntry(
        transcript_model="large-v3",
        transcript_source=TranscriptSource.YOUTUBE,
        llm_provider="openai",
        llm_model="gpt-4o",
        worker="batch-1",
        at="2026-06-10T14:00:00+00:00",
        extra={"run": "abc", "shard": "1"},
    )
    out = extraction_history_entry_from_dict(extraction_history_entry_to_dict(e))
    assert out == e


def test_extraction_history_entry_to_dict_camelcase():
    e = ExtractionHistoryEntry(
        transcript_model="m",
        transcript_source=TranscriptSource.YOUTUBE,
        llm_provider="anthropic",
        llm_model="x",
        worker="w",
        at="2026-06-10T14:00:00Z",
    )
    d = extraction_history_entry_to_dict(e)
    assert d["transcriptModel"] == "m"
    assert d["transcriptSource"] == "youtube"
    assert d["llmProvider"] == "anthropic"
    assert d["llmModel"] == "x"
    assert d["worker"] == "w"
    assert d["at"] == "2026-06-10T14:00:00Z"


def test_extraction_history_entry_to_dict_omits_empty_extra():
    e = ExtractionHistoryEntry(
        transcript_model=None,
        transcript_source=None,
        llm_provider="a",
        llm_model="x",
        worker=None,
        at="2026-06-10T14:00:00Z",
    )
    d = extraction_history_entry_to_dict(e)
    assert "extra" not in d


def test_extraction_history_entry_from_dict_default_extra():
    d = {
        "transcriptModel": None,
        "transcriptSource": None,
        "llmProvider": "a",
        "llmModel": "x",
        "worker": None,
        "at": "2026-06-10T14:00:00Z",
    }
    e = extraction_history_entry_from_dict(d)
    assert dict(e.extra) == {}


# ---------------------------------------------------------------------------
# Mention — round-trip
# ---------------------------------------------------------------------------


def _mk_mention(**overrides):
    defaults = dict(
        id="m-001",
        item_id="abc12345",
        source_ref=SourceRef(source_id="ubm", episode_guid="e1"),
    )
    defaults.update(overrides)
    return Mention(**defaults)


def test_mention_round_trip_minimal():
    m = _mk_mention()
    assert mention_from_dict(mention_to_dict(m)) == m


def test_mention_round_trip_full():
    m = _mk_mention(
        recommended_by="Kyan",
        quote="J'ai adoré",
        kind=MentionKind.CITATION,
        status=MentionStatus.VALIDATED,
        extraction_history=(
            ExtractionHistoryEntry(
                transcript_model="large-v3",
                transcript_source=TranscriptSource.YOUTUBE,
                llm_provider="anthropic",
                llm_model="claude-3",
                worker="w1",
                at="2026-06-10T14:00:00Z",
                extra={"k": "v"},
            ),
        ),
        extractors=("anthropic", "openai"),
        schema_version=2,
    )
    assert mention_from_dict(mention_to_dict(m)) == m


# ---------------------------------------------------------------------------
# Mention — to_dict
# ---------------------------------------------------------------------------


def test_mention_to_dict_camelcase():
    m = _mk_mention()
    d = mention_to_dict(m)
    assert "itemId" in d
    assert "sourceRef" in d
    assert "schemaVersion" in d


def test_mention_to_dict_omits_none_and_empty():
    m = _mk_mention()
    d = mention_to_dict(m)
    assert "recommendedBy" not in d
    assert "quote" not in d
    assert "extractionHistory" not in d
    assert "extractors" not in d


def test_mention_to_dict_includes_defaults_kind_status():
    m = _mk_mention()
    d = mention_to_dict(m)
    assert d["kind"] == "reco"
    assert d["status"] == "draft"


def test_mention_to_dict_extractors_serialized_as_list():
    m = _mk_mention(extractors=("a", "b"))
    d = mention_to_dict(m)
    assert d["extractors"] == ["a", "b"]


def test_mention_to_dict_extraction_history_serialized():
    e = ExtractionHistoryEntry(
        transcript_model=None,
        transcript_source=None,
        llm_provider="anthropic",
        llm_model="x",
        worker=None,
        at="2026-06-10T14:00:00Z",
    )
    m = _mk_mention(extraction_history=(e,))
    d = mention_to_dict(m)
    assert isinstance(d["extractionHistory"], list)
    assert d["extractionHistory"][0]["llmProvider"] == "anthropic"


# ---------------------------------------------------------------------------
# Mention — from_dict
# ---------------------------------------------------------------------------


def test_mention_from_dict_missing_id_raises():
    with pytest.raises((KeyError, ValueError)):
        mention_from_dict({
            "itemId": "abc12345",
            "sourceRef": {"sourceId": "x"},
        })


def test_mention_from_dict_missing_item_id_raises():
    with pytest.raises((KeyError, ValueError)):
        mention_from_dict({
            "id": "m-1",
            "sourceRef": {"sourceId": "x"},
        })


def test_mention_from_dict_missing_source_ref_raises():
    with pytest.raises((KeyError, ValueError)):
        mention_from_dict({"id": "m-1", "itemId": "abc12345"})


def test_mention_from_dict_unknown_field_tolerated():
    d = mention_to_dict(_mk_mention())
    d["futureField"] = "ignored"
    m = mention_from_dict(d)
    assert m.id == "m-001"


def test_mention_unknown_field_logged_with_warning(caplog):
    """A11 — Forward-compat capture."""
    import logging
    d = mention_to_dict(_mk_mention())
    d["futureA"] = 1
    d["futureB"] = "x"
    with caplog.at_level(logging.WARNING, logger="repository.serialization.mention_codec"):
        mention_from_dict(d)
    msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("champs inconnus" in m and "futureA" in m and "futureB" in m for m in msgs)
    assert any("m-001" in m for m in msgs)


def test_mention_known_fields_no_warning(caplog):
    """A11 — Pas de warning si tous les champs sont reconnus."""
    import logging
    d = mention_to_dict(_mk_mention())
    with caplog.at_level(logging.WARNING, logger="repository.serialization.mention_codec"):
        mention_from_dict(d)
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_mention_from_dict_default_kind_status():
    d = {
        "id": "m-1",
        "itemId": "abc12345",
        "sourceRef": {"sourceId": "x"},
    }
    m = mention_from_dict(d)
    assert m.kind == MentionKind.RECO
    assert m.status == MentionStatus.DRAFT


def test_mention_from_dict_default_schema_version():
    d = {
        "id": "m-1",
        "itemId": "abc12345",
        "sourceRef": {"sourceId": "x"},
    }
    m = mention_from_dict(d)
    assert m.schema_version == 1


def test_mention_from_dict_extractors_as_tuple():
    d = {
        "id": "m-1",
        "itemId": "abc12345",
        "sourceRef": {"sourceId": "x"},
        "extractors": ["a", "b"],
    }
    m = mention_from_dict(d)
    assert m.extractors == ("a", "b")


def test_mention_from_dict_full_extraction_history():
    d = {
        "id": "m-1",
        "itemId": "abc12345",
        "sourceRef": {"sourceId": "x"},
        "extractionHistory": [
            {
                "transcriptModel": "large-v3",
                "transcriptSource": "youtube",
                "llmProvider": "anthropic",
                "llmModel": "claude-3",
                "worker": "w1",
                "at": "2026-06-10T14:00:00Z",
                "extra": {"k": "v"},
            }
        ],
    }
    m = mention_from_dict(d)
    assert len(m.extraction_history) == 1
    assert m.extraction_history[0].llm_provider == "anthropic"
    assert dict(m.extraction_history[0].extra) == {"k": "v"}
