"""Services métier purs (zéro IO) opérant sur les entités du domaine.

Réexports pratiques pour les callsites qui préfèrent
`from domain.services import canonical_key` à
`from domain.services.identity import canonical_key`.
"""
from .compatibility import can_attach_mention, can_merge_items
from .identity import (
    IdentityRegistry,
    ItemIdentityService,
    canonical_key,
    find_matching_item,
    generate_item_id,
)

__all__ = [
    "canonical_key",
    "generate_item_id",
    "find_matching_item",
    "IdentityRegistry",
    "ItemIdentityService",
    "can_merge_items",
    "can_attach_mention",
]
