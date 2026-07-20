"""
migration — Conversion des recos legacy (`src/content/recos/`) vers la
nouvelle représentation `Item` + `Mention`.

Architecture (SOLID / Clean Arch) :

- `reco_parser.reco_dict_to_item_mention(reco, *, item_id_resolver)` —
  fonction **pure** (zéro IO) qui convertit un dict legacy en
  `(Item, Mention)`. Le `item_id` est délégué à un *resolver* injecté pour
  ne pas violer le SRP (le parser ne connaît pas le repository).
- `reco_to_item_mention.MigrationService` — orchestration : lit les recos
  d'un dossier source, parse, déduplique via les repos injectés, écrit
  les Items + Mentions. Dependency-Inversion : ne dépend que des
  `Protocol`s `ItemRepository` / `MentionRepository`.

Voir docstring de chaque module pour les invariants.
"""
from __future__ import annotations

from .reco_parser import reco_dict_to_item_mention
from .reco_to_item_mention import MigrationService, MigrationStats

__all__ = [
    "reco_dict_to_item_mention",
    "MigrationService",
    "MigrationStats",
]
