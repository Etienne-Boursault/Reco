"""
compatibility.py — Règles de compatibilité entre entités du domaine.

Décisions pures (zéro IO) :
  - `can_merge_items(a, b)` : deux `Item` représentent-ils la même œuvre ?
  - `can_attach_mention(mention, item)` : la `Mention` cible-t-elle bien
    cet `Item` ?

Pas d'heuristique floue ici (similarité textuelle, scoring…) — la couche
domaine ne raisonne que sur des invariants stricts. Les heuristiques
restent dans les services applicatifs (`tools/reco_dedup.py` etc.).
"""
from __future__ import annotations

from ..item import ExternalIds, Item
from ..mention import Mention
from .identity import canonical_key


def _external_ids_compatible(a: ExternalIds, b: ExternalIds) -> bool:
    """True si aucun champ identifiant n'est en conflit (les None ne comptent pas)."""
    fields = ("tmdb", "tmdb_type", "spotify", "musicbrainz", "openlibrary", "isbn", "justwatch")
    for f in fields:
        va = getattr(a, f)
        vb = getattr(b, f)
        if va is not None and vb is not None and va != vb:
            return False
    return True


def can_merge_items(a: Item, b: Item) -> bool:
    """Décide si deux `Item` représentent la même œuvre et peuvent être fusionnés.

    Règles strictes (cf. ADR 0002) :
      1. Même `canonical_key` (title + creator normalisés, types exclus).
      2. Intersection non vide des `types` (ex. un FILM et un LIVRE
         portant le même titre/créateur ne sont PAS la même œuvre).
      3. `external_ids` compatibles (aucun conflit sur champs définis
         des deux côtés).

    Args:
        a: Premier Item.
        b: Deuxième Item.

    Returns:
        True si les deux items représentent la même œuvre.
    """
    if not isinstance(a, Item) or not isinstance(b, Item):
        raise ValueError("can_merge_items: a et b doivent être des Item")

    # 1. canonical (title + creator uniquement, cf. ADR 0002)
    if canonical_key(a.title, a.creator) != canonical_key(b.title, b.creator):
        return False

    # 2. intersection des types non vide
    if not (set(a.types) & set(b.types)):
        return False

    # 3. external_ids compatibles
    if not _external_ids_compatible(a.external_ids, b.external_ids):
        return False

    return True


def can_attach_mention(mention: Mention, item: Item) -> bool:
    """True ssi `mention.item_id == item.id`.

    Args:
        mention: La mention candidate.
        item: L'item cible.
    """
    if not isinstance(mention, Mention) or not isinstance(item, Item):
        raise ValueError("can_attach_mention: types invalides")
    return mention.item_id == item.id


__all__ = ["can_merge_items", "can_attach_mention"]
