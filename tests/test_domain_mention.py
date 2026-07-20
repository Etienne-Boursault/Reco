"""Tests de `tools.domain.mention` — couverture 100% (couche pure, zéro IO)."""
from __future__ import annotations

import dataclasses

import pytest

from domain.mention import (
    ExtractionHistoryEntry,
    Mention,
    MentionKind,
    MentionStatus,
    SourceRef,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_mention_kind_values():
    assert MentionKind.RECO == "reco"
    assert MentionKind.CITATION == "citation"


def test_mention_status_values():
    assert MentionStatus.DRAFT == "draft"
    assert MentionStatus.VALIDATED == "validated"
    assert MentionStatus.DISCARDED == "discarded"


# ---------------------------------------------------------------------------
# SourceRef
# ---------------------------------------------------------------------------


def test_source_ref_minimal_ok():
    s = SourceRef(source_id="ubm")
    assert s.episode_guid is None
    assert s.timestamp is None
    assert s.transcript_source is None


def test_source_ref_full_ok():
    s = SourceRef(
        source_id="ubm",
        episode_guid="guid-1",
        timestamp="01:23:45",
        transcript_source="youtube",
    )
    assert s.timestamp == "01:23:45"
    assert s.transcript_source == "youtube"


def test_source_ref_empty_source_id_raises():
    with pytest.raises(ValueError, match="source_id"):
        SourceRef(source_id="")


def test_source_ref_blank_source_id_raises():
    with pytest.raises(ValueError, match="source_id"):
        SourceRef(source_id="   ")


def test_source_ref_non_str_source_id_raises():
    with pytest.raises(ValueError, match="source_id"):
        SourceRef(source_id=123)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_ts",
    [
        "1:23:45",     # HH manquant zéro
        "01:23",       # pas de SS
        "01:23:45.1",  # millisecondes interdites
        "abc",
        "01-23-45",
        " 01:23:45",
        "01:23:45 ",
    ],
)
def test_source_ref_invalid_timestamp_raises(bad_ts):
    with pytest.raises(ValueError, match="timestamp"):
        SourceRef(source_id="x", timestamp=bad_ts)


def test_source_ref_timestamp_none_ok():
    SourceRef(source_id="x", timestamp=None)


def test_source_ref_invalid_transcript_source_raises():
    with pytest.raises(ValueError, match="transcript_source"):
        SourceRef(source_id="x", transcript_source="whisper")


@pytest.mark.parametrize("ts_src", [None, "youtube", "acast"])
def test_source_ref_valid_transcript_sources(ts_src):
    SourceRef(source_id="x", transcript_source=ts_src)


def test_source_ref_is_frozen():
    s = SourceRef(source_id="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.source_id = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ExtractionHistoryEntry
# ---------------------------------------------------------------------------


def _make_entry(**overrides):
    base = dict(
        transcript_model="whisper-large-v3",
        transcript_source="youtube",
        llm_provider="anthropic",
        llm_model="claude-3-5-sonnet",
        worker="worker-1",
        at="2026-06-10T14:00:00Z",
    )
    base.update(overrides)
    return ExtractionHistoryEntry(**base)


def test_extraction_history_entry_minimal_ok():
    e = _make_entry()
    assert e.llm_provider == "anthropic"
    assert e.extra == {}


def test_extraction_history_entry_with_extra():
    e = _make_entry(extra={"retry": "2"})
    assert e.extra["retry"] == "2"


def test_extraction_history_entry_nullable_fields_ok():
    e = _make_entry(transcript_model=None, transcript_source=None, worker=None)
    assert e.transcript_model is None
    assert e.transcript_source is None
    assert e.worker is None


def test_extraction_history_entry_empty_llm_provider_raises():
    with pytest.raises(ValueError, match="llm_provider"):
        _make_entry(llm_provider="")


def test_extraction_history_entry_blank_llm_provider_raises():
    with pytest.raises(ValueError, match="llm_provider"):
        _make_entry(llm_provider="   ")


def test_extraction_history_entry_empty_llm_model_raises():
    with pytest.raises(ValueError, match="llm_model"):
        _make_entry(llm_model="")


def test_extraction_history_entry_blank_llm_model_raises():
    with pytest.raises(ValueError, match="llm_model"):
        _make_entry(llm_model="   ")


def test_extraction_history_entry_empty_at_raises():
    with pytest.raises(ValueError, match="at"):
        _make_entry(at="")


def test_extraction_history_entry_blank_at_raises():
    with pytest.raises(ValueError, match="at"):
        _make_entry(at="   ")


def test_extraction_history_entry_invalid_transcript_source_raises():
    with pytest.raises(ValueError, match="transcript_source"):
        _make_entry(transcript_source="whisper")


def test_extraction_history_entry_is_frozen():
    e = _make_entry()
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.llm_provider = "openai"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Mention
# ---------------------------------------------------------------------------


def _make_mention(**overrides):
    base = dict(
        id="m-1",
        item_id="abc12345",
        source_ref=SourceRef(source_id="ubm"),
    )
    base.update(overrides)
    return Mention(**base)


def test_mention_minimal_ok():
    m = _make_mention()
    assert m.recommended_by is None
    assert m.quote is None
    assert m.kind == MentionKind.RECO
    assert m.status == MentionStatus.DRAFT
    assert m.extraction_history == ()
    assert m.extractors == ()
    assert m.schema_version == 1


def test_mention_with_all_fields():
    entry = _make_entry()
    m = _make_mention(
        recommended_by="Pierre",
        quote="Très bon film.",
        kind=MentionKind.CITATION,
        status=MentionStatus.VALIDATED,
        extraction_history=(entry,),
        extractors=("anthropic",),
        schema_version=2,
    )
    assert m.recommended_by == "Pierre"
    assert m.kind == MentionKind.CITATION
    assert m.status == MentionStatus.VALIDATED
    assert m.extraction_history == (entry,)
    assert m.extractors == ("anthropic",)
    assert m.schema_version == 2


# --- validation ---


def test_mention_empty_id_raises():
    with pytest.raises(ValueError, match="id"):
        _make_mention(id="")


def test_mention_blank_id_raises():
    with pytest.raises(ValueError, match="id"):
        _make_mention(id="   ")


def test_mention_non_str_id_raises():
    with pytest.raises(ValueError, match="id"):
        _make_mention(id=42)  # type: ignore[arg-type]


def test_mention_empty_item_id_raises():
    with pytest.raises(ValueError, match="item_id"):
        _make_mention(item_id="")


def test_mention_blank_item_id_raises():
    with pytest.raises(ValueError, match="item_id"):
        _make_mention(item_id="   ")


def test_mention_non_str_item_id_raises():
    with pytest.raises(ValueError, match="item_id"):
        _make_mention(item_id=42)  # type: ignore[arg-type]


# C2 — item_id regex validation (anti path-traversal).
@pytest.mark.parametrize("bad", [
    "../etc/passwd",
    "abc/def",
    "abc\\def",
    "ABC123",
    "abc_123",
    "abc 123",
    "a" * 65,
    "------",
    "-abc",
    "abc-",
    "a--b",
])
def test_mention_invalid_item_id_format_raises(bad):
    """C2 — item_id doit respecter la même regex qu'Item.id."""
    with pytest.raises(ValueError, match="item_id"):
        _make_mention(item_id=bad)


def test_mention_source_ref_must_be_source_ref():
    with pytest.raises(ValueError, match="source_ref"):
        _make_mention(source_ref={"source_id": "x"})  # type: ignore[arg-type]


def test_mention_kind_must_be_mention_kind():
    with pytest.raises(ValueError, match="kind"):
        _make_mention(kind="reco")  # type: ignore[arg-type]


def test_mention_status_must_be_mention_status():
    with pytest.raises(ValueError, match="status"):
        _make_mention(status="draft")  # type: ignore[arg-type]


def test_mention_extraction_history_must_be_tuple():
    with pytest.raises(ValueError, match="extraction_history"):
        _make_mention(extraction_history=[_make_entry()])  # type: ignore[arg-type]


def test_mention_extraction_history_only_entries():
    with pytest.raises(ValueError, match="extraction_history"):
        _make_mention(extraction_history=("not-an-entry",))  # type: ignore[arg-type]


def test_mention_extractors_must_be_tuple():
    with pytest.raises(ValueError, match="extractors"):
        _make_mention(extractors=["anthropic"])  # type: ignore[arg-type]


def test_mention_extractors_blank_string_raises():
    with pytest.raises(ValueError, match="extractors"):
        _make_mention(extractors=("",))


def test_mention_extractors_non_str_raises():
    with pytest.raises(ValueError, match="extractors"):
        _make_mention(extractors=(42,))  # type: ignore[arg-type]


def test_mention_schema_version_zero_raises():
    with pytest.raises(ValueError, match="schema_version"):
        _make_mention(schema_version=0)


def test_mention_schema_version_non_int_raises():
    with pytest.raises(ValueError, match="schema_version"):
        _make_mention(schema_version="1")  # type: ignore[arg-type]


def test_mention_schema_version_bool_raises():
    with pytest.raises(ValueError, match="schema_version"):
        _make_mention(schema_version=True)  # type: ignore[arg-type]


def test_mention_is_frozen():
    m = _make_mention()
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.id = "other"  # type: ignore[misc]


def test_mention_equality():
    a = _make_mention()
    b = _make_mention()
    assert a == b
