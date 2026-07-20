"""
tools.repository.serialization — Codecs Item/Mention ↔ dict JSON (purs).

Zéro IO. Toutes les fonctions sont déterministes et idempotentes :
`from_dict(to_dict(x)) == x` pour tout `x` valide.

Convention : clés JSON en camelCase pour cohérence avec les schémas
Astro/Zod (cf. `src/content.config.ts`).
"""
from __future__ import annotations

from .item_codec import item_from_dict, item_to_dict
from .mention_codec import (
    extraction_history_entry_from_dict,
    extraction_history_entry_to_dict,
    mention_from_dict,
    mention_to_dict,
    source_ref_from_dict,
    source_ref_to_dict,
)

__all__ = [
    "item_from_dict",
    "item_to_dict",
    "mention_from_dict",
    "mention_to_dict",
    "source_ref_from_dict",
    "source_ref_to_dict",
    "extraction_history_entry_from_dict",
    "extraction_history_entry_to_dict",
]
