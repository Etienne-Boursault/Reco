"""tools.cache — Cache d'index SQLite (read-through depuis JSON, FTS5).

Architecture (cf. ADR 0020) :

- `schema`     : DDL (tables + index + virtual tables FTS5 + metadata).
- `builder`    : `CacheBuilder` lit les JSON `src/content/{items,mentions,episodes}/`
                 et insère dans une base SQLite atomique.
- `reader`     : `CacheReader` accès lecture seule (`mode=ro`) avec API typée.
- `fts`        : helpers de sanitisation FTS5 (`fts_query`) + snippets BM25.
- `ports`      : Protocols pour DIP (`CacheBackend`, `JsonLoader`).
- `descriptor` : `EntityDescriptor` (ADR 0026 — OCP pattern).

API publique stable. Tout le reste est interne (préfixe `_`).
"""
from __future__ import annotations

from cache.builder import BuildReport, BuildStats, CacheBuilder
from cache.descriptor import EntityDescriptor
from cache.fts import fts_query
from cache.ports import CacheBackend, JsonLoader
from cache.reader import CacheReader, EpisodeRow, ItemRow, MentionRow, SearchHit
from cache.schema import (
    CACHE_SCHEMA_VERSION,
    CacheCorruptedError,
    FTS5NotAvailableError,
    StaleCacheError,
    create_schema,
)

__all__ = [
    "CACHE_SCHEMA_VERSION",
    "BuildReport",
    "BuildStats",
    "CacheBackend",
    "CacheBuilder",
    "CacheCorruptedError",
    "CacheReader",
    "EntityDescriptor",
    "EpisodeRow",
    "FTS5NotAvailableError",
    "ItemRow",
    "JsonLoader",
    "MentionRow",
    "SearchHit",
    "StaleCacheError",
    "create_schema",
    "fts_query",
]
