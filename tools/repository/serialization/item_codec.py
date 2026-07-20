"""
item_codec.py — Sérialisation pure `Item` ↔ `dict` JSON-compatible.

Zéro IO, zéro dépendance externe. Le contrat :
  - `item_to_dict(item)` produit un dict camelCase prêt pour `json.dumps`.
  - `item_from_dict(data)` accepte ce dict (ou un sur-ensemble — forward
    compat soft : les champs inconnus sont ignorés).
  - `item_from_dict(item_to_dict(x)) == x` pour tout Item valide.

Les invariants métier (id regex, year bornes, etc.) restent assurés
par `Item.__post_init__` — le codec ne fait que le mapping nom/struct.
"""
from __future__ import annotations

import logging
from typing import Any

from domain.item import (
    CustomLink,
    ExternalIds,
    Item,
    ItemType,
    WatchProvider,
)

_log = logging.getLogger(__name__)

# Champs camelCase reconnus par `item_from_dict`. Tout autre clé sera loggée
# en WARNING (forward compat soft — pas une exception).
_KNOWN_ITEM_FIELDS: frozenset[str] = frozenset({
    "id",
    "types",
    "title",
    "creator",
    "year",
    "aliases",
    "externalIds",
    "customLinks",
    "watchProviders",
    "linkOverrides",
    "recommendedBy",
    "schemaVersion",
})


# ---------------------------------------------------------------------------
# ExternalIds
# ---------------------------------------------------------------------------


def _external_ids_to_dict(ext: ExternalIds) -> dict[str, Any]:
    """Sérialise ExternalIds en dict camelCase. Champs None omis."""
    out: dict[str, Any] = {}
    if ext.tmdb is not None:
        out["tmdb"] = ext.tmdb
    if ext.tmdb_type is not None:
        out["tmdbType"] = ext.tmdb_type
    if ext.spotify is not None:
        out["spotify"] = ext.spotify
    if ext.musicbrainz is not None:
        out["musicbrainz"] = ext.musicbrainz
    if ext.openlibrary is not None:
        out["openlibrary"] = ext.openlibrary
    if ext.isbn is not None:
        out["isbn"] = ext.isbn
    if ext.justwatch is not None:
        out["justwatch"] = ext.justwatch
    return out


def _external_ids_from_dict(data: dict[str, Any]) -> ExternalIds:
    return ExternalIds(
        tmdb=data.get("tmdb"),
        tmdb_type=data.get("tmdbType"),
        spotify=data.get("spotify"),
        musicbrainz=data.get("musicbrainz"),
        openlibrary=data.get("openlibrary"),
        isbn=data.get("isbn"),
        justwatch=data.get("justwatch"),
    )


# ---------------------------------------------------------------------------
# WatchProvider / CustomLink
# ---------------------------------------------------------------------------


def _watch_provider_to_dict(wp: WatchProvider) -> dict[str, Any]:
    out: dict[str, Any] = {"name": wp.name, "url": wp.url}
    if wp.region is not None:
        out["region"] = wp.region
    if wp.ethics is not None:
        out["ethics"] = wp.ethics
    return out


def _watch_provider_from_dict(data: dict[str, Any]) -> WatchProvider:
    return WatchProvider(
        name=data["name"],
        url=data["url"],
        region=data.get("region"),
        ethics=data.get("ethics"),
    )


def _custom_link_to_dict(cl: CustomLink) -> dict[str, Any]:
    return {"label": cl.label, "url": cl.url}


def _custom_link_from_dict(data: dict[str, Any]) -> CustomLink:
    return CustomLink(label=data["label"], url=data["url"])


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------


def item_to_dict(item: Item) -> dict[str, Any]:
    """Sérialise un Item en dict JSON-compatible (camelCase).

    Champs `None` ou collections vides → omis pour produire un JSON
    minimal cohérent avec Zod `.optional()` côté Astro.
    """
    out: dict[str, Any] = {
        "id": item.id,
        "types": [t.value for t in item.types],
        "title": item.title,
        "schemaVersion": item.schema_version,
    }
    if item.creator is not None:
        out["creator"] = item.creator
    if item.year is not None:
        out["year"] = item.year
    if item.aliases:
        out["aliases"] = list(item.aliases)
    ext_dict = _external_ids_to_dict(item.external_ids)
    if ext_dict:
        out["externalIds"] = ext_dict
    if item.custom_links:
        out["customLinks"] = [_custom_link_to_dict(cl) for cl in item.custom_links]
    if item.watch_providers:
        out["watchProviders"] = [
            _watch_provider_to_dict(wp) for wp in item.watch_providers
        ]
    if item.link_overrides:
        out["linkOverrides"] = dict(item.link_overrides)
    if item.recommended_by is not None:
        out["recommendedBy"] = item.recommended_by
    return out


def item_from_dict(data: dict[str, Any]) -> Item:
    """Désérialise un dict en Item. Champs inconnus ignorés (forward compat).

    Raises:
        KeyError: si un champ requis manque (id, types, title).
        ValueError: si une valeur est invalide (cf. `Item.__post_init__`).
    """
    unknown = set(data.keys()) - _KNOWN_ITEM_FIELDS
    if unknown:
        _log.warning(
            "item_from_dict: champs inconnus ignorés %s (id=%s)",
            sorted(unknown),
            data.get("id"),
        )
    types_raw = data["types"]
    types = tuple(ItemType(t) for t in types_raw)

    ext = (
        _external_ids_from_dict(data["externalIds"])
        if "externalIds" in data
        else ExternalIds()
    )
    custom_links = tuple(
        _custom_link_from_dict(d) for d in data.get("customLinks", ())
    )
    watch_providers = tuple(
        _watch_provider_from_dict(d) for d in data.get("watchProviders", ())
    )
    aliases = tuple(data.get("aliases", ()))
    link_overrides = dict(data.get("linkOverrides", {}))

    return Item(
        id=data["id"],
        types=types,
        title=data["title"],
        creator=data.get("creator"),
        year=data.get("year"),
        aliases=aliases,
        external_ids=ext,
        custom_links=custom_links,
        watch_providers=watch_providers,
        link_overrides=link_overrides,
        recommended_by=data.get("recommendedBy"),
        schema_version=data.get("schemaVersion", 1),
    )


__all__ = ["item_to_dict", "item_from_dict"]
