"""
mention_codec.py — Sérialisation pure `Mention` ↔ `dict` JSON-compatible.

Zéro IO. Convention camelCase (cohérence Astro/Zod).
"""
from __future__ import annotations

import logging
from typing import Any

from domain.mention import (
    ExtractionHistoryEntry,
    Mention,
    MentionKind,
    MentionStatus,
    SourceRef,
    TranscriptSource,
)

_log = logging.getLogger(__name__)

_KNOWN_MENTION_FIELDS: frozenset[str] = frozenset({
    "id",
    "itemId",
    "sourceRef",
    "recommendedBy",
    "quote",
    "kind",
    "status",
    "extractionHistory",
    "extractors",
    "schemaVersion",
})


# ---------------------------------------------------------------------------
# SourceRef
# ---------------------------------------------------------------------------


def source_ref_to_dict(sr: SourceRef) -> dict[str, Any]:
    """Sérialise SourceRef. Champs None omis."""
    out: dict[str, Any] = {"sourceId": sr.source_id}
    if sr.episode_guid is not None:
        out["episodeGuid"] = sr.episode_guid
    if sr.timestamp is not None:
        out["timestamp"] = sr.timestamp
    if sr.transcript_source is not None:
        out["transcriptSource"] = sr.transcript_source.value
    return out


def source_ref_from_dict(data: dict[str, Any]) -> SourceRef:
    ts_raw = data.get("transcriptSource")
    ts = TranscriptSource(ts_raw) if ts_raw is not None else None
    return SourceRef(
        source_id=data["sourceId"],
        episode_guid=data.get("episodeGuid"),
        timestamp=data.get("timestamp"),
        transcript_source=ts,
    )


# ---------------------------------------------------------------------------
# ExtractionHistoryEntry
# ---------------------------------------------------------------------------


def extraction_history_entry_to_dict(e: ExtractionHistoryEntry) -> dict[str, Any]:
    """Sérialise une entrée d'historique. `extra` vide omis."""
    # `transcript_source` est TranscriptSource ou None (coercion garantie par
    # `_coerce_transcript_source` du domaine — cf. domain/mention.py).
    ts_value: str | None = (
        e.transcript_source.value if e.transcript_source is not None else None
    )

    out: dict[str, Any] = {
        "transcriptModel": e.transcript_model,
        "transcriptSource": ts_value,
        "llmProvider": e.llm_provider,
        "llmModel": e.llm_model,
        "worker": e.worker,
        "at": e.at,
    }
    if e.extra:
        out["extra"] = dict(e.extra)
    return out


def extraction_history_entry_from_dict(
    data: dict[str, Any],
) -> ExtractionHistoryEntry:
    return ExtractionHistoryEntry(
        transcript_model=data.get("transcriptModel"),
        transcript_source=data.get("transcriptSource"),
        llm_provider=data["llmProvider"],
        llm_model=data["llmModel"],
        worker=data.get("worker"),
        at=data["at"],
        extra=dict(data.get("extra", {})),
    )


# ---------------------------------------------------------------------------
# Mention
# ---------------------------------------------------------------------------


def mention_to_dict(m: Mention) -> dict[str, Any]:
    """Sérialise une Mention en dict camelCase JSON-compatible."""
    out: dict[str, Any] = {
        "id": m.id,
        "itemId": m.item_id,
        "sourceRef": source_ref_to_dict(m.source_ref),
        "kind": m.kind.value,
        "status": m.status.value,
        "schemaVersion": m.schema_version,
    }
    if m.recommended_by is not None:
        out["recommendedBy"] = m.recommended_by
    if m.quote is not None:
        out["quote"] = m.quote
    if m.extraction_history:
        out["extractionHistory"] = [
            extraction_history_entry_to_dict(e) for e in m.extraction_history
        ]
    if m.extractors:
        out["extractors"] = list(m.extractors)
    return out


def mention_from_dict(data: dict[str, Any]) -> Mention:
    """Désérialise un dict en Mention. Champs inconnus ignorés (forward compat)."""
    unknown = set(data.keys()) - _KNOWN_MENTION_FIELDS
    if unknown:
        _log.warning(
            "mention_from_dict: champs inconnus ignorés %s (id=%s)",
            sorted(unknown),
            data.get("id"),
        )
    sr = source_ref_from_dict(data["sourceRef"])
    history = tuple(
        extraction_history_entry_from_dict(d)
        for d in data.get("extractionHistory", ())
    )
    extractors = tuple(data.get("extractors", ()))
    kind = MentionKind(data.get("kind", MentionKind.RECO.value))
    status = MentionStatus(data.get("status", MentionStatus.DRAFT.value))

    return Mention(
        id=data["id"],
        item_id=data["itemId"],
        source_ref=sr,
        recommended_by=data.get("recommendedBy"),
        quote=data.get("quote"),
        kind=kind,
        status=status,
        extraction_history=history,
        extractors=extractors,
        schema_version=data.get("schemaVersion", 1),
    )


__all__ = [
    "source_ref_to_dict",
    "source_ref_from_dict",
    "extraction_history_entry_to_dict",
    "extraction_history_entry_from_dict",
    "mention_to_dict",
    "mention_from_dict",
]
