"""
mention.py — Entité `Mention` (référence à un Item dans un épisode).

Une `Mention` est l'**occurrence** d'un `Item` dans le transcript d'un
épisode : qui l'a recommandée/évoquée, à quel timestamp, avec quelle
citation. Elle pointe vers l'`Item` via `item_id` — l'Item lui-même est
agrégé séparément (cf. `tools/domain/item.py`).

Pure logique de domaine — **aucune dépendance IO**. Validation à la
construction → `ValueError`.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MentionKind(StrEnum):
    """Distingue une œuvre recommandée d'une œuvre simplement évoquée."""

    RECO = "reco"
    CITATION = "citation"


class MentionStatus(StrEnum):
    """État éditorial d'une mention dans le workflow de review."""

    DRAFT = "draft"
    VALIDATED = "validated"
    DISCARDED = "discarded"


class TranscriptSource(StrEnum):
    """Origine du transcript utilisé pour extraire la mention.

    Cf. mémoire utilisateur : YouTube est la source par défaut, Acast en
    repli. JAMAIS d'offset entre les deux.
    """

    YOUTUBE = "youtube"
    ACAST = "acast"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


_TIMESTAMP_PATTERN = re.compile(r"^(\d{2}):(\d{2}):(\d{2})$")
# C2 — Aligné sur `Item._ID_PATTERN` (anti path-traversal, anti `------`).
_ITEM_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ITEM_ID_MAX_LEN = 64


def _coerce_transcript_source(value: object) -> TranscriptSource | None:
    """Normalise une valeur en TranscriptSource (accepte str pour compat)."""
    if value is None:
        return None
    if isinstance(value, TranscriptSource):
        return value
    if isinstance(value, str):
        try:
            return TranscriptSource(value)
        except ValueError as e:
            raise ValueError(
                f"transcript_source invalide: {value!r}; "
                f"attendu None, 'youtube' ou 'acast'"
            ) from e
    raise ValueError(
        f"transcript_source invalide: {value!r}; "
        f"attendu None, str ('youtube'|'acast') ou TranscriptSource"
    )


@dataclass(frozen=True)
class SourceRef:
    """Localisation d'une mention dans une source (podcast, épisode, timestamp)."""

    source_id: str
    episode_guid: str | None = None
    timestamp: str | None = None         # "HH:MM:SS"
    transcript_source: TranscriptSource | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("SourceRef.source_id ne peut pas être vide")
        if self.timestamp is not None:
            m = _TIMESTAMP_PATTERN.match(self.timestamp)
            if not m:
                raise ValueError(
                    f"SourceRef.timestamp invalide: {self.timestamp!r}; "
                    "attendu HH:MM:SS"
                )
            # Archi #13 : valider 0<=mm<60, 0<=ss<60.
            _, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if mm >= 60 or ss >= 60:
                raise ValueError(
                    f"SourceRef.timestamp hors bornes: {self.timestamp!r}; "
                    "MM et SS doivent être < 60"
                )
        # Coercition transcript_source → TranscriptSource (compat str).
        coerced = _coerce_transcript_source(self.transcript_source)
        if coerced is not self.transcript_source:
            object.__setattr__(self, "transcript_source", coerced)


@dataclass(frozen=True)
class ExtractionHistoryEntry:
    """Trace d'une passe d'extraction (LLM + worker + horodatage)."""

    transcript_model: str | None
    transcript_source: str | None
    llm_provider: str
    llm_model: str
    worker: str | None
    at: str   # ISO timestamp, ex "2026-06-10T14:00:00Z"
    # C3 — Élargi à scalaires JSON (str|int|float|bool) pour permettre
    # `pos_in_transcript`, `score`, etc. sans coercion préalable.
    extra: Mapping[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.llm_provider, str) or not self.llm_provider.strip():
            raise ValueError("ExtractionHistoryEntry.llm_provider ne peut pas être vide")
        if not isinstance(self.llm_model, str) or not self.llm_model.strip():
            raise ValueError("ExtractionHistoryEntry.llm_model ne peut pas être vide")
        if not isinstance(self.at, str) or not self.at.strip():
            raise ValueError("ExtractionHistoryEntry.at ne peut pas être vide")
        # Senior L9 : valider format ISO8601 minimal.
        # Accepte aussi le suffix 'Z' (zulu) pour rétro-compat — datetime
        # ne le supporte qu'à partir de 3.11.
        iso_candidate = self.at.replace("Z", "+00:00") if self.at.endswith("Z") else self.at
        try:
            datetime.fromisoformat(iso_candidate)
        except ValueError as e:
            raise ValueError(
                f"ExtractionHistoryEntry.at doit être ISO8601: {self.at!r}"
            ) from e
        # Coercition transcript_source.
        coerced = _coerce_transcript_source(self.transcript_source)
        if coerced is not self.transcript_source:
            object.__setattr__(self, "transcript_source", coerced)
        # Validation + freeze de `extra`.
        if not isinstance(self.extra, Mapping):
            raise ValueError(
                f"ExtractionHistoryEntry.extra doit être un Mapping, "
                f"reçu {type(self.extra).__name__}"
            )
        for k, v in self.extra.items():
            if not isinstance(k, str):
                raise ValueError(
                    f"ExtractionHistoryEntry.extra : clé invalide {k!r}, str requis"
                )
            # C3 — Accepte scalaires JSON : str, int, float, bool.
            # bool est sous-type d'int en Python, donc on accepte explicitement
            # via `(int, float, str, bool)` sans rejet spécial.
            if not isinstance(v, (str, int, float, bool)):
                raise ValueError(
                    f"ExtractionHistoryEntry.extra : valeur invalide ({k!r}: {v!r}), "
                    "attendu str | int | float | bool"
                )
        object.__setattr__(self, "extra", MappingProxyType(dict(self.extra)))


# ---------------------------------------------------------------------------
# Mention
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mention:
    """Occurrence d'un Item dans un épisode — agrégat immuable.

    Invariants :
      - `id` / `item_id` non vides
      - `source_ref` validé (cf. SourceRef)
      - `kind` ∈ MentionKind, `status` ∈ MentionStatus
      - `extraction_history` / `extractors` : tuples
      - `schema_version` >= 1
    """

    id: str
    item_id: str
    source_ref: SourceRef
    recommended_by: str | None = None
    quote: str | None = None
    kind: MentionKind = MentionKind.RECO
    status: MentionStatus = MentionStatus.DRAFT
    extraction_history: tuple[ExtractionHistoryEntry, ...] = ()
    extractors: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Mention.id ne peut pas être vide")
        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise ValueError("Mention.item_id ne peut pas être vide")
        # C2 — Valider via la regex d'Item.id (anti path-traversal).
        if (
            len(self.item_id) > _ITEM_ID_MAX_LEN
            or not _ITEM_ID_PATTERN.match(self.item_id)
        ):
            raise ValueError(
                f"Mention.item_id invalide: {self.item_id!r}; "
                f"attendu ^[a-z0-9]+(-[a-z0-9]+)*$ (max {_ITEM_ID_MAX_LEN} chars)"
            )
        if not isinstance(self.source_ref, SourceRef):
            raise ValueError("Mention.source_ref doit être une SourceRef")
        # recommended_by : None ou str non-blank.
        if self.recommended_by is not None and (
            not isinstance(self.recommended_by, str)
            or not self.recommended_by.strip()
        ):
            raise ValueError(
                "Mention.recommended_by doit être None ou une chaîne non vide"
            )
        # quote : None ou str non-blank.
        if self.quote is not None and (
            not isinstance(self.quote, str) or not self.quote.strip()
        ):
            raise ValueError(
                "Mention.quote doit être None ou une chaîne non vide"
            )
        if not isinstance(self.kind, MentionKind):
            raise ValueError(
                f"Mention.kind doit être MentionKind, reçu {type(self.kind).__name__}"
            )
        if not isinstance(self.status, MentionStatus):
            raise ValueError(
                f"Mention.status doit être MentionStatus, "
                f"reçu {type(self.status).__name__}"
            )
        if not isinstance(self.extraction_history, tuple):
            raise ValueError("Mention.extraction_history doit être un tuple")
        for entry in self.extraction_history:
            if not isinstance(entry, ExtractionHistoryEntry):
                raise ValueError(
                    "Mention.extraction_history ne doit contenir que des "
                    "ExtractionHistoryEntry"
                )
        if not isinstance(self.extractors, tuple):
            raise ValueError("Mention.extractors doit être un tuple")
        for extr in self.extractors:
            if not isinstance(extr, str) or not extr.strip():
                raise ValueError("Mention.extractors ne doit pas contenir de chaîne vide")
        if not isinstance(self.schema_version, int) or isinstance(
            self.schema_version, bool
        ):
            raise ValueError("Mention.schema_version doit être un int")
        if self.schema_version < 1:
            raise ValueError(
                f"Mention.schema_version doit être >= 1, reçu {self.schema_version}"
            )


__all__ = [
    "MentionKind",
    "MentionStatus",
    "TranscriptSource",
    "SourceRef",
    "ExtractionHistoryEntry",
    "Mention",
]
