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
    "CustomLink",
    "Episode",
    "EpisodeRepository",
    "ExternalIds",
    "ExtractionHistoryEntry",
    "IdentityRegistry",
    # new (item)
    "Item",
    "ItemIdentityService",
    "ItemType",
    "LLMExtractor",
    # new (mention)
    "Mention",
    "MentionKind",
    "MentionStatus",
    "RSSClient",
    "Reco",
    "RecoKind",
    "RecoRepository",
    "RecoStatus",
    "RecoType",
    # legacy
    "Source",
    "SourceRef",
    "TranscriberEngine",
    "TranscriptSegment",
    "TranscriptSource",
    "TranscriptStore",
    "VisionOCR",
    "WatchProvider",
    "YouTubeClient",
    "can_attach_mention",
    "can_merge_items",
    # new (services)
    "canonical_key",
    "find_matching_item",
    "generate_item_id",
]
