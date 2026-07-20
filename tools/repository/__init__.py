"""
tools.repository — Couche infrastructure (Clean Architecture).

Implémentations concrètes des ports `ItemRepository` / `MentionRepository`
définis dans `tools.domain.ports`. Persistance JSON-on-disk via
`common.atomic_write_text` (Windows-safe).

Sous-modules :
  - `repository.item_repo` : `ItemRepoJson`
  - `repository.mention_repo` : `MentionRepoJson`
  - `repository.serialization` : codecs purs (zéro IO)
"""
from __future__ import annotations

from .item_repo import ItemRepoJson
from .mention_repo import MentionRepoJson

__all__ = ["ItemRepoJson", "MentionRepoJson"]
