"""
tools.domain — Couche domaine pure (Clean Architecture).

Ce package contient les entités et services métier **sans aucune
dépendance IO** (pas de fichier, pas de réseau, pas de processus
externe). Il est testable à 100% et constitue le cœur stable du
projet Reco.

Historiquement, `tools/domain.py` exposait `Source`, `Episode`,
`Reco`, `TranscriptSegment` et plusieurs `Protocol` (ports
hexagonaux). Ces symboles restent réexportés depuis ce package
pour préserver les imports existants (`from domain import Reco`).

Nouvelle couche (Phase 1 item 2.A) :
  - `Item` / `ItemType` / `ExternalIds` / `WatchProvider` / `CustomLink`
  - `Mention` / `SourceRef` / `MentionKind` / `MentionStatus` /
    `ExtractionHistoryEntry`
  - services :
      * `canonical_key`, `ItemIdentityService`
      * `can_merge_items`, `can_attach_mention`
"""
from __future__ import annotations

from ._legacy import (
    Episode,
    EpisodeRepository,
    LLMExtractor,
    Reco,
    RecoKind,
    RecoRepository,
    RecoStatus,
    RecoType,
    RSSClient,
    Source,
    TranscriberEngine,
    TranscriptSegment,
    TranscriptStore,
    VisionOCR,
    YouTubeClient,
)
from .item import CustomLink, ExternalIds, Item, ItemType, WatchProvider
from .mention import (
    ExtractionHistoryEntry,
    Mention,
    MentionKind,
    MentionStatus,
    SourceRef,
    TranscriptSource,
)
from .services.compatibility import can_attach_mention, can_merge_items
from .services.identity import (
    IdentityRegistry,
    ItemIdentityService,
    canonical_key,
    find_matching_item,
    generate_item_id,
)

__all__ = [
    # legacy
    "Source",
    "Episode",
    "Reco",
    "TranscriptSegment",
    "RecoStatus",
    "RecoKind",
    "RecoType",
    "EpisodeRepository",
    "RecoRepository",
    "TranscriptStore",
    "RSSClient",
    "YouTubeClient",
    "TranscriberEngine",
    "LLMExtractor",
    "VisionOCR",
    # new (item)
    "Item",
    "ItemType",
    "ExternalIds",
    "WatchProvider",
    "CustomLink",
    # new (mention)
    "Mention",
    "SourceRef",
    "MentionKind",
    "MentionStatus",
    "TranscriptSource",
    "ExtractionHistoryEntry",
    # new (services)
    "canonical_key",
    "generate_item_id",
    "find_matching_item",
    "IdentityRegistry",
    "ItemIdentityService",
    "can_merge_items",
    "can_attach_mention",
]
