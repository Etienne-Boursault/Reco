"""cache.reader — Lecture read-only du cache SQLite.

Ouvre la connexion en `mode=ro` via URI. Pas d'écriture.
Le read-through (`get_item_or_rebuild`) délègue au builder fourni si la
mtime du fichier source dépasse celle stockée en cache.

Cohérence multi-thread
----------------------
``check_same_thread=False`` (CR senior M13) : la connexion étant
read-only, l'usage cross-thread reste sûr pour les workflows Astro /
SSG qui lisent depuis plusieurs handlers.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from cache.fts import fts_query
from cache.schema import (
    CACHE_SCHEMA_VERSION,
    CacheCorruptedError,
    StaleCacheError,
)

# ``mode=ro`` : pas d'écriture, mais ``immutable=0`` (défaut) — un writer
# externe peut modifier le fichier (read-through / rebuild incrémental).
_RO_URI_TEMPLATE: Final[str] = "file:{path}?mode=ro"


@dataclass(frozen=True, slots=True)
class ItemRow:
    """Ligne `items` projetée — immutable."""

    source_id: str
    id: str
    schema_version: int
    title: str
    types: tuple[str, ...]
    canonical_key: str | None
    external_ids: Mapping[str, Any] | None
    enrichment_suspect: bool
    json_path: str
    json_mtime: float


@dataclass(frozen=True, slots=True)
class MentionRow:
    """Ligne `mentions` projetée — immutable."""

    source_id: str
    id: str
    schema_version: int
    item_id: str
    episode_guid: str
    timestamp_seconds: int | None
    recommended_by: str | None
    quote: str | None
    json_path: str
    json_mtime: float


@dataclass(frozen=True, slots=True)
class EpisodeRow:
    """Ligne `episodes` projetée — immutable."""

    source_id: str
    guid: str
    schema_version: int
    title: str | None
    hosts: tuple[str, ...]
    guests: tuple[str, ...]
    guests_parsed: tuple[str, ...]
    match_suspect: bool
    json_path: str
    json_mtime: float


@dataclass(frozen=True, slots=True)
class SearchHit:
    """Résultat FTS5 : identifiant + score BM25 (faible = meilleur)."""

    source_id: str
    id: str
    title: str
    rank: float


def _row_to_item(row: sqlite3.Row) -> ItemRow:
    raw_ext = row["external_ids"]
    external_ids = json.loads(raw_ext) if raw_ext else None
    return ItemRow(
        source_id=row["source_id"],
        id=row["id"],
        schema_version=row["schema_version"],
        title=row["title"],
        types=tuple(json.loads(row["types"])),
        canonical_key=row["canonical_key"],
        external_ids=MappingProxyType(external_ids) if external_ids else None,
        enrichment_suspect=bool(row["enrichment_suspect"]),
        json_path=row["json_path"],
        json_mtime=float(row["json_mtime"]),
    )


def _row_to_mention(row: sqlite3.Row) -> MentionRow:
    return MentionRow(
        source_id=row["source_id"],
        id=row["id"],
        schema_version=row["schema_version"],
        item_id=row["item_id"],
        episode_guid=row["episode_guid"],
        timestamp_seconds=row["timestamp_seconds"],
        recommended_by=row["recommended_by"],
        quote=row["quote"],
        json_path=row["json_path"],
        json_mtime=float(row["json_mtime"]),
    )


def _row_to_episode(row: sqlite3.Row) -> EpisodeRow:
    return EpisodeRow(
        source_id=row["source_id"],
        guid=row["guid"],
        schema_version=row["schema_version"],
        title=row["title"],
        hosts=tuple(json.loads(row["hosts"] or "[]")),
        guests=tuple(json.loads(row["guests"] or "[]")),
        guests_parsed=tuple(json.loads(row["guests_parsed"] or "[]")),
        match_suspect=bool(row["match_suspect"]),
        json_path=row["json_path"],
        json_mtime=float(row["json_mtime"]),
    )


class CacheReader:
    """Lecture read-only du cache SQLite.

    Ouvre la connexion en mode RO via URI sqlite. Toute tentative
    d'écriture lèvera `sqlite3.OperationalError("attempt to write a readonly database")`.

    Validations à l'ouverture (CR senior C2/H7/M4) :
      - le fichier doit exister ;
      - le header SQLite doit être valide (sinon :class:`CacheCorruptedError`) ;
      - ``cache_schema_version`` doit matcher (sinon :class:`StaleCacheError`).
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Cache absent : {self.db_path}. "
                f"Lance `python tools/build_cache.py` d'abord."
            )
        self._check_sqlite_header(self.db_path)
        uri = _RO_URI_TEMPLATE.format(path=self.db_path.as_posix())
        self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._validate_schema_version()

    @staticmethod
    def _check_sqlite_header(path: Path) -> None:
        try:
            with path.open("rb") as fh:
                header = fh.read(16)
        except OSError as exc:  # pragma: no cover - defensive
            raise CacheCorruptedError(
                f"Impossible de lire {path}: {exc}"
            ) from exc
        if not header.startswith(b"SQLite format 3"):
            raise CacheCorruptedError(
                f"Le fichier {path} n'est pas une base SQLite valide. "
                f"Rebuild via `python tools/build_cache.py`."
            )

    def _validate_schema_version(self) -> None:
        try:
            cur = self._conn.execute(
                "SELECT value FROM cache_meta WHERE key = 'cache_schema_version'"
            )
            row = cur.fetchone()
        except sqlite3.DatabaseError as exc:
            raise CacheCorruptedError(
                f"cache_meta inaccessible: {exc}. "
                f"Rebuild via `python tools/build_cache.py`."
            ) from exc
        if row is None:
            raise StaleCacheError(
                "cache_schema_version absent — rebuild via "
                "`python tools/build_cache.py`."
            )
        try:
            stored = int(row["value"])
        except (TypeError, ValueError) as exc:
            raise CacheCorruptedError(
                f"cache_schema_version illisible: {row['value']!r}"
            ) from exc
        if stored != CACHE_SCHEMA_VERSION:
            raise StaleCacheError(
                f"Cache schema v{stored} ≠ attendu v{CACHE_SCHEMA_VERSION}. "
                f"Rebuild via `python tools/build_cache.py`."
            )

    def close(self) -> None:
        """Ferme la connexion. Idempotent."""
        try:
            self._conn.close()
        except sqlite3.ProgrammingError:
            pass

    def __enter__(self) -> CacheReader:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ----- Items -----

    def get_item(self, source_id: str, item_id: str) -> ItemRow | None:
        cur = self._conn.execute(
            "SELECT * FROM items WHERE source_id = ? AND id = ?",
            (source_id, item_id),
        )
        row = cur.fetchone()
        return _row_to_item(row) if row else None

    def iter_items(
        self,
        source_id: str,
        *,
        only_suspect: bool = False,
        item_type: str | None = None,
        guest: str | None = None,
    ) -> Iterator[ItemRow]:
        """Itère les items d'une source.

        Filtres optionnels (CR archi P2-9) :
            only_suspect : ``enrichment_suspect=1`` uniquement.
            item_type    : présence dans ``items.types`` (JSON array).
            guest        : item dont au moins une mention pointe un épisode
                           où ce guest est listé dans ``guests_parsed``.
        """
        clauses = ["i.source_id = ?"]
        params: list[Any] = [source_id]
        if only_suspect:
            clauses.append("i.enrichment_suspect = 1")
        if item_type is not None:
            # JSON_EACH sur le tableau ``types`` ; LIKE pour rester
            # tolérant casse via LOWER ne s'applique pas (case-sensitive).
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(i.types) t WHERE t.value = ?)"
            )
            params.append(item_type)
        if guest is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM mentions m "
                "JOIN episodes e ON e.source_id = m.source_id AND e.guid = m.episode_guid "
                "JOIN json_each(e.guests_parsed) g "
                "WHERE m.source_id = i.source_id AND m.item_id = i.id "
                "AND g.value = ?)"
            )
            params.append(guest)
        # S608 écarté : `clauses` ne contient que des littéraux définis dans
        # cette fonction ; TOUTES les valeurs passent par `params` et les
        # placeholders `?`. Aucune donnée externe n'entre dans le SQL.
        sql = f"SELECT i.* FROM items i WHERE {' AND '.join(clauses)} ORDER BY i.id"  # noqa: S608
        cur = self._conn.execute(sql, params)
        for row in cur:
            yield _row_to_item(row)

    # ----- Mentions -----

    def get_mentions_for_item(self, source_id: str, item_id: str) -> list[MentionRow]:
        cur = self._conn.execute(
            "SELECT * FROM mentions WHERE source_id = ? AND item_id = ? ORDER BY id",
            (source_id, item_id),
        )
        return [_row_to_mention(r) for r in cur]

    def get_mentions_for_episode(
        self, source_id: str, episode_guid: str
    ) -> list[MentionRow]:
        cur = self._conn.execute(
            "SELECT * FROM mentions WHERE source_id = ? AND episode_guid = ? ORDER BY id",
            (source_id, episode_guid),
        )
        return [_row_to_mention(r) for r in cur]

    # ----- Episodes -----

    def get_episode(self, source_id: str, guid: str) -> EpisodeRow | None:
        cur = self._conn.execute(
            "SELECT * FROM episodes WHERE source_id = ? AND guid = ?",
            (source_id, guid),
        )
        row = cur.fetchone()
        return _row_to_episode(row) if row else None

    # ----- FTS5 -----

    def search_items(
        self,
        query: str,
        *,
        limit: int = 20,
        source_id: str | None = None,
        column: str | None = None,
    ) -> list[SearchHit]:
        """Recherche FTS5 sur items.

        Args:
            query      : texte utilisateur (sanitizé par ``fts_query``).
            limit      : nombre max de hits.
            source_id  : si fourni, filtre côté SQL via colonne ``source_id``
                         UNINDEXED (élimine le post-filter Python — CR senior H8).
            column     : si fourni, restreint à une colonne FTS5
                         (``title`` / ``recommended_by`` / ``guests_text``)
                         pour une recherche multi-critère (CR archi P1-2).
        """
        match = fts_query(query, column=column)
        if source_id is None:
            sql = (
                "SELECT f.source_id, f.id, i.title, f.rank "
                "FROM items_fts f "
                "JOIN items i ON i.source_id = f.source_id AND i.id = f.id "
                "WHERE items_fts MATCH ? "
                "ORDER BY f.rank LIMIT ?"
            )
            params: tuple[Any, ...] = (match, limit)
        else:
            sql = (
                "SELECT f.source_id, f.id, i.title, f.rank "
                "FROM items_fts f "
                "JOIN items i ON i.source_id = f.source_id AND i.id = f.id "
                "WHERE items_fts MATCH ? AND f.source_id = ? "
                "ORDER BY f.rank LIMIT ?"
            )
            params = (match, source_id, limit)
        cur = self._conn.execute(sql, params)
        return [
            SearchHit(
                source_id=r["source_id"],
                id=r["id"],
                title=r["title"],
                rank=float(r["rank"]),
            )
            for r in cur
        ]

    def search_episodes(
        self,
        query: str,
        *,
        limit: int = 20,
        source_id: str | None = None,
        column: str | None = None,
    ) -> list[SearchHit]:
        """Recherche FTS5 sur episodes (title + hosts + guests).

        ``SearchHit.id`` contient le guid de l'épisode. Cf. ``search_items``
        pour le détail des arguments.
        """
        match = fts_query(query, column=column)
        if source_id is None:
            sql = (
                "SELECT f.source_id, f.guid AS id, e.title, f.rank "
                "FROM episodes_fts f "
                "JOIN episodes e ON e.source_id = f.source_id AND e.guid = f.guid "
                "WHERE episodes_fts MATCH ? "
                "ORDER BY f.rank LIMIT ?"
            )
            params: tuple[Any, ...] = (match, limit)
        else:
            sql = (
                "SELECT f.source_id, f.guid AS id, e.title, f.rank "
                "FROM episodes_fts f "
                "JOIN episodes e ON e.source_id = f.source_id AND e.guid = f.guid "
                "WHERE episodes_fts MATCH ? AND f.source_id = ? "
                "ORDER BY f.rank LIMIT ?"
            )
            params = (match, source_id, limit)
        cur = self._conn.execute(sql, params)
        return [
            SearchHit(
                source_id=r["source_id"],
                id=r["id"],
                title=r["title"] or "",
                rank=float(r["rank"]),
            )
            for r in cur
        ]

    # ----- Metadata -----

    def get_meta(self, key: str) -> str | None:
        cur = self._conn.execute(
            "SELECT value FROM cache_meta WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        return row["value"] if row else None

    # ----- Read-through (mtime invalidation) -----

    def get_item_or_rebuild(
        self,
        source_id: str,
        item_id: str,
        *,
        builder: Any,
    ) -> ItemRow | None:
        """Lit le cache. Si la mtime du JSON a changé, déclenche un refresh
        incrémental via `builder.refresh_item_file(...)`, puis relit.

        Implémente un pattern ``stat → read → stat-recheck`` simplifié
        (CR senior H2) : on lit, on déclenche le refresh une seule fois.
        Si la mtime continue de bouger entre l'éveil du writer et la
        relecture, on stocke la mtime observée au refresh (et non
        l'instantanée — ce qui évite les boucles infinies).

        Important : le ``builder`` ouvre sa propre connexion RW. En
        contexte multi-process / serveur (cf. ADR 0020 § Read-through),
        il appartient au caller de tenir le ``pipeline_lock`` si une
        sérialisation est nécessaire (CR senior H1 / CR archi P1-4).
        """
        row = self.get_item(source_id, item_id)
        if row is None:
            return None
        json_path = Path(row.json_path)
        if not json_path.exists():
            return row
        try:
            actual_mtime = json_path.stat().st_mtime
        except OSError:  # pragma: no cover - race
            return row
        if actual_mtime <= row.json_mtime + 1e-6:
            return row
        # Stale → refresh.
        builder.refresh_item_file(source_id, item_id, json_path)
        # Relit après refresh.
        return self.get_item(source_id, item_id)
