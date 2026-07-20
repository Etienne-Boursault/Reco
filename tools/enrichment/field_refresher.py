"""Field refresher — partial update préservant les champs non touchés.

Règle : si on rafraîchit `runtime` seul, on ne touche PAS à `providers_watch`
(potentiellement édité à la main par un humain).

Aussi : maintient l'audit trail dans `item["enrichedAt"][field] = now_iso`.

Le module est pur (pas d'IO réseau ni disque) — il prend un item dict en
mémoire, applique la mise à jour, retourne l'item modifié IN-PLACE.
"""
from __future__ import annotations

from typing import Any

from .tracker import now_iso


class EnrichedAtCorruptedError(ValueError):
    """`item["enrichedAt"]` existe mais n'est pas un dict — on refuse d'écraser.

    P0-5 : protection contre la corruption silencieuse du audit trail.
    Avant ce fix, un `enrichedAt` non-dict (ex. string accidentelle)
    était écrasé par `{}` lors d'un `partial_update`, supprimant tout
    l'historique d'enrichissement de l'item. On lève désormais une
    exception pour que le caller skip l'item au lieu de détruire l'audit.

    Re-exportée depuis `enrichment` (cf. `enrichment.__init__`).
    """


def _check_enrichedat_dict(item: dict) -> None:
    """P0-5 : refuse d'écraser un `enrichedAt` non-dict (corruption)."""
    ea = item.get("enrichedAt")
    if ea is not None and not isinstance(ea, dict):
        raise EnrichedAtCorruptedError(
            f"item {item.get('id', '?')} a enrichedAt non-dict: "
            f"{type(ea).__name__}",
        )


def partial_update(
    item: dict,
    field: str,
    new_value: Any,
    *,
    timestamp: str | None = None,
    delete_if_none: bool = False,
) -> dict:
    """Met à jour `item[field]` et trace `item["enrichedAt"][field]`.

    Args:
        item: dict modifié IN-PLACE.
        field: nom du champ top-level (ex. "runtime", "year",
               "watchProviders"). Pour les champs nested, le caller doit
               aplatir (ex. clé "externalIds.tmdb" gérée par
               `update_nested`).
        new_value: nouvelle valeur. Si None et delete_if_none=True, supprime
                   le champ existant.
        timestamp: ISO8601 à stocker. Défaut = now_iso().
        delete_if_none: si True, `new_value=None` supprime le champ existant
                        et trace tout de même l'opération dans enrichedAt
                        (audit : "on a vérifié, le provider n'a plus rien").

    Retourne : l'item (même référence).

    Lève `EnrichedAtCorruptedError` si `item["enrichedAt"]` existe et n'est
    pas un dict (cf. P0-5).
    """
    _check_enrichedat_dict(item)
    ts = timestamp or now_iso()

    if new_value is None and delete_if_none:
        item.pop(field, None)
    elif new_value is not None:
        item[field] = new_value
    else:
        # new_value is None and not delete_if_none → no-op sur la valeur,
        # mais on trace quand même (l'enrichissement a eu lieu sans hit).
        pass

    ea = item.get("enrichedAt")
    if not isinstance(ea, dict):
        ea = {}
    ea[field] = ts
    item["enrichedAt"] = ea
    return item


def update_nested(
    item: dict,
    path: str,
    new_value: Any,
    *,
    timestamp: str | None = None,
) -> dict:
    """Variante pour champs imbriqués via chemin pointé (ex. "externalIds.tmdb").

    Crée les dicts parents au besoin. Trace `enrichedAt[path] = timestamp`
    avec la clé complète (forme plate, pour rester sérialisable JSON).

    Lève `EnrichedAtCorruptedError` si `item["enrichedAt"]` existe et n'est
    pas un dict (cf. P0-5).
    """
    _check_enrichedat_dict(item)
    ts = timestamp or now_iso()
    parts = path.split(".")
    cursor = item
    for p in parts[:-1]:
        nxt = cursor.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[p] = nxt
        cursor = nxt
    cursor[parts[-1]] = new_value

    ea = item.get("enrichedAt")
    if not isinstance(ea, dict):
        ea = {}
    ea[path] = ts
    item["enrichedAt"] = ea
    return item
