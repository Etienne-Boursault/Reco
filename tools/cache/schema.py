"""cache.schema — DDL du cache SQLite (tables + FTS5 + metadata).

Centralise toutes les instructions `CREATE` afin de garantir un schéma
unique réutilisé par le builder, les tests, et toute migration future.

Version du schéma : `CACHE_SCHEMA_VERSION` — bump => rebuild obligatoire.

Historique des versions
-----------------------
* v1 (Phase 2 vague 1 P2.8 initial) : schéma de base.
* v2 (Phase 2 vague 1 P2.8 hardening) : ajoute
    - index partiel `idx_items_suspect` filtré sur ``enrichment_suspect=1``
      (au lieu d'un index couvrant — plus efficace, cf. CR senior M8) ;
    - index `idx_items_canonical` sur ``canonical_key`` filtré non-NULL
      (CR archi P2-8) ;
    - colonne ``mentions.recommended_by_norm`` (TEXT) — normalisée
      ``LOWER(TRIM(...))`` côté builder (CR senior H6) ;
    - `cache_meta` étendu (sémantique) : ``built_for_sources``,
      ``git_sha``, ``fingerprint`` (CR archi M12 / P2-6) ;
    - FK ``mentions(source_id, item_id) → items`` désormais activée à
      l'ouverture via ``PRAGMA foreign_keys = ON`` (CR senior C3).
"""
from __future__ import annotations

import sqlite3
from typing import Final

CACHE_SCHEMA_VERSION: Final[int] = 2

# Ordre des CREATE : tables physiques d'abord (pour FK), puis FTS5, puis meta.
_CREATE_ITEMS: Final[str] = """
CREATE TABLE items (
  source_id TEXT NOT NULL,
  id TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  title TEXT NOT NULL,
  types TEXT NOT NULL,
  canonical_key TEXT,
  external_ids TEXT,
  enrichment_suspect INTEGER NOT NULL DEFAULT 0,
  json_path TEXT NOT NULL,
  json_mtime REAL NOT NULL,
  PRIMARY KEY (source_id, id)
)
"""

_CREATE_MENTIONS: Final[str] = """
CREATE TABLE mentions (
  source_id TEXT NOT NULL,
  id TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  item_id TEXT NOT NULL,
  episode_guid TEXT NOT NULL,
  timestamp_seconds INTEGER,
  recommended_by TEXT,
  recommended_by_norm TEXT,
  quote TEXT,
  json_path TEXT NOT NULL,
  json_mtime REAL NOT NULL,
  PRIMARY KEY (source_id, id),
  FOREIGN KEY (source_id, item_id) REFERENCES items(source_id, id)
)
"""

_CREATE_EPISODES: Final[str] = """
CREATE TABLE episodes (
  source_id TEXT NOT NULL,
  guid TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  title TEXT,
  hosts TEXT,
  guests TEXT,
  guests_parsed TEXT,
  match_suspect INTEGER NOT NULL DEFAULT 0,
  json_path TEXT NOT NULL,
  json_mtime REAL NOT NULL,
  PRIMARY KEY (source_id, guid)
)
"""

_CREATE_CACHE_META: Final[str] = """
CREATE TABLE cache_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
)
"""

# Index : accélère les lookups par item_id (mentions → item) et episode_guid.
_CREATE_IDX_MENTIONS_ITEM: Final[str] = (
    "CREATE INDEX idx_mentions_item ON mentions(source_id, item_id)"
)
_CREATE_IDX_MENTIONS_EPISODE: Final[str] = (
    "CREATE INDEX idx_mentions_episode ON mentions(source_id, episode_guid)"
)
# Partial index : suspect=1 minoritaire (~5-10%). Filtré → index ~10× plus
# petit, lookup `WHERE enrichment_suspect=1` direct (CR senior M8).
_CREATE_IDX_ITEMS_SUSPECT: Final[str] = (
    "CREATE INDEX idx_items_suspect ON items(source_id) "
    "WHERE enrichment_suspect = 1"
)
# canonical_key non-NULL minoritaire ; index partiel pour lookups de
# dédoublonnage cross-source (CR archi P2-8).
_CREATE_IDX_ITEMS_CANONICAL: Final[str] = (
    "CREATE INDEX idx_items_canonical ON items(canonical_key) "
    "WHERE canonical_key IS NOT NULL"
)

# FTS5 — tokenizer unicode61 + remove_diacritics (essentiel pour le FR).
# `source_id` UNINDEXED mais filtrable côté SQL via `WHERE` (cf. CR senior H8).
_CREATE_ITEMS_FTS: Final[str] = """
CREATE VIRTUAL TABLE items_fts USING fts5(
  source_id UNINDEXED,
  id UNINDEXED,
  title,
  recommended_by,
  guests_text,
  tokenize = 'unicode61 remove_diacritics 2'
)
"""

_CREATE_EPISODES_FTS: Final[str] = """
CREATE VIRTUAL TABLE episodes_fts USING fts5(
  source_id UNINDEXED,
  guid UNINDEXED,
  title,
  hosts_text,
  guests_text,
  tokenize = 'unicode61 remove_diacritics 2'
)
"""

_ALL_STATEMENTS: Final[tuple[str, ...]] = (
    _CREATE_ITEMS,
    _CREATE_MENTIONS,
    _CREATE_EPISODES,
    _CREATE_CACHE_META,
    _CREATE_IDX_MENTIONS_ITEM,
    _CREATE_IDX_MENTIONS_EPISODE,
    _CREATE_IDX_ITEMS_SUSPECT,
    _CREATE_IDX_ITEMS_CANONICAL,
    _CREATE_ITEMS_FTS,
    _CREATE_EPISODES_FTS,
)


class FTS5NotAvailableError(RuntimeError):
    """FTS5 absent du build SQLite local (cf. ADR 0020 § Prérequis)."""


class StaleCacheError(RuntimeError):
    """Cache présent mais ``cache_schema_version`` divergente."""


class CacheCorruptedError(RuntimeError):
    """Le fichier n'est pas une base SQLite valide ou manque les tables."""


def check_fts5_available() -> None:
    """Vérifie que FTS5 est compilé dans la libsqlite locale.

    Lève :func:`FTS5NotAvailableError` si absent.
    """
    conn = sqlite3.connect(":memory:")
    try:
        opts = {row[0] for row in conn.execute("PRAGMA compile_options")}
    finally:
        conn.close()
    if "ENABLE_FTS5" not in opts:
        raise FTS5NotAvailableError(
            "FTS5 n'est pas disponible dans cette installation SQLite. "
            "Voir ADR 0020 § Prérequis (Python compilé avec --enable-fts5 "
            "ou libsqlite ≥ 3.20 avec FTS5 activé)."
        )


def create_schema(conn: sqlite3.Connection) -> None:
    """Crée toutes les tables / index / vtables FTS5 sur la connexion fournie.

    Idempotent uniquement si la base est neuve : si une table existe déjà,
    sqlite lèvera `sqlite3.OperationalError`. Le builder DROP toujours
    avant d'appeler `create_schema` pour garantir l'idempotence des
    rebuilds complets.
    """
    cur = conn.cursor()
    for stmt in _ALL_STATEMENTS:
        cur.execute(stmt)
    conn.commit()


def drop_schema(conn: sqlite3.Connection) -> None:
    """Supprime toutes les tables/vtables du cache. Idempotent (IF EXISTS)."""
    cur = conn.cursor()
    # FTS5 d'abord (peut être lié à shadow tables).
    for tbl in ("items_fts", "episodes_fts"):
        cur.execute(f"DROP TABLE IF EXISTS {tbl}")
    for tbl in ("mentions", "items", "episodes", "cache_meta"):
        cur.execute(f"DROP TABLE IF EXISTS {tbl}")
    conn.commit()
