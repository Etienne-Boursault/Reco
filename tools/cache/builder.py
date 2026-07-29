"""cache.builder — Construit la base SQLite à partir des JSON `src/content/`.

Stratégie : rebuild atomique (`<db>.tmp` → `os.replace`). Lit tous les
fichiers JSON, INSERT par batch (``executemany``) dans tables physiques
+ FTS5. Pas de parallélisme (sqlite single-writer, et les volumes restent
modestes : ~3000 lignes/s sur disque local).

Idempotence : un rebuild complet recrée le fichier from scratch ; un
rebuild incrémental (`refresh_item_file`) supprime puis réinsère une ligne.

Sécurité / corruption
---------------------
* ``synchronous = NORMAL`` (et non ``OFF``) : tient au crash sans
  corruption silencieuse, perf équivalente avec ``journal_mode=MEMORY``
  pour un build one-shot (CR senior C1).
* FTS5 vérifié à l'ouverture (CR senior C2).
* Foreign keys activées (``PRAGMA foreign_keys = ON``) sur les
  connexions du builder pour rejeter les mentions orphelines
  (CR senior C3).
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from cache.schema import (
    CACHE_SCHEMA_VERSION,
    check_fts5_available,
    create_schema,
    drop_schema,
)

# Nom du builder injecté dans cache_meta (debug).
_BUILDER_TAG: Final[str] = __name__


@dataclass(frozen=True, slots=True)
class BuildStats:
    """Statistiques d'un rebuild — frozen, immutable.

    ``duration_s`` couvre uniquement la phase build (INSERT + FTS +
    meta). ``vacuum()`` / ``optimize()`` sont logués séparément
    (CR senior M11).
    """

    n_items: int
    n_mentions: int
    n_episodes: int
    n_fts_rows: int
    duration_s: float


@dataclass(slots=True)
class BuildReport:
    """Rapport d'un build : stats + erreurs non-fatales (JSON malformés).

    Les fichiers qui échouent au parse sont loggés et listés ici plutôt
    que de planter le build (CR archi P2-4).
    """

    stats: BuildStats | None = None
    errors: list[str] = field(default_factory=list)


# ---------- JsonLoader filesystem par défaut --------------------------------


class _FsJsonLoader:
    """Loader JSON filesystem par défaut (implémente `JsonLoader` Protocol)."""

    def iter_files(self, root: Path) -> Iterable[Path]:
        if not root.exists():
            return ()
        return sorted(p for p in root.iterdir() if p.is_file() and p.suffix == ".json")

    def read(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def mtime(self, path: Path) -> float:
        return path.stat().st_mtime


# ---------- Helpers conversion ---------------------------------------------


def _parse_timestamp_to_seconds(ts: Any) -> int | None:
    """Convertit `'HH:MM:SS'`, `'HH:MM:SS.mmm'` ou `int` en secondes."""
    if ts is None:
        return None
    if isinstance(ts, bool):
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    if isinstance(ts, str):
        parts = ts.split(":")
        try:
            # Accepte ``HH:MM:SS.mmm`` en tronquant la partie décimale
            # (CR senior L5).
            ints = [int(p.split(".")[0]) for p in parts]
        except ValueError:
            return None
        if len(ints) == 3:
            h, m, s = ints
            return h * 3600 + m * 60 + s
        if len(ints) == 2:
            m, s = ints
            return m * 60 + s
        if len(ints) == 1:
            return ints[0]
    return None


def _json_dump(value: Any) -> str:
    """Sérialise une valeur en JSON compact (UTF-8 conservé)."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalize_recommended_by(name: Any) -> str | None:
    """Normalise ``recommended_by`` pour dédoublonnage (CR senior H6).

    Trim + collapse whitespace + lowercase. ``None``/vide → ``None``.
    """
    if name is None:
        return None
    if not isinstance(name, str):
        return None
    cleaned = " ".join(name.split()).strip().lower()
    return cleaned or None


def _safe_str_list(value: Any) -> list[str]:
    """Convertit une valeur JSON en liste de strings nettoyée."""
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if x is not None and str(x).strip()]


def _try_git_sha() -> str | None:
    """Best-effort ``git rev-parse HEAD``. Retourne ``None`` si Git absent."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).resolve().parent,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    sha = out.stdout.strip()
    return sha or None


# ---------- CacheBuilder ----------------------------------------------------


class CacheBuilder:
    """Construit le cache SQLite à partir des dossiers JSON.

    Paramètres :
      db_path      : chemin final de la base.
      items_dir    : racine des items (`src/content/items/`).
      mentions_dir : racine des mentions (`src/content/mentions/`).
      episodes_dir : racine des épisodes (`src/content/episodes/`).
      loader       : `JsonLoader` injectable (DIP). Par défaut: filesystem.
      logger       : optionnel — fonction (msg, *args) appelée pour les
                     warnings (JSON malformé, skip ``__``). Défaut : print.

    Le builder écrit dans `<db_path>.tmp` puis `os.replace` → atomique.
    """

    def __init__(
        self,
        db_path: Path,
        items_dir: Path,
        mentions_dir: Path,
        episodes_dir: Path,
        *,
        loader: Any = None,
        logger: Any = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.items_dir = Path(items_dir)
        self.mentions_dir = Path(mentions_dir)
        self.episodes_dir = Path(episodes_dir)
        self.loader = loader if loader is not None else _FsJsonLoader()
        self._log = logger
        # Rapport courant — alimenté par les phases ``_load_*``.
        self._errors: list[str] = []

    def _warn(self, msg: str, *args: Any) -> None:
        if self._log is not None:
            try:
                self._log(msg, *args)
                return
            except Exception:  # noqa: BLE001, S110 — un logger défaillant
                pass  # ne doit pas faire échouer un build ; on retombe sur stderr.
        # Fallback discret : stderr.
        try:
            print(msg % args if args else msg)
        except Exception:  # noqa: BLE001, S110 — dernier recours : si même
            pass  # stderr est indisponible, il n'y a plus rien à tenter.

    # ----- Connexion utilitaire (FK + pragmas perf) -----

    def _open_rw(self, path: Path, *, fast: bool) -> sqlite3.Connection:
        conn = sqlite3.connect(str(path))
        # FK activées sur toutes les écritures (CR senior C3).
        conn.execute("PRAGMA foreign_keys = ON")
        if fast:
            # CR senior C1 : NORMAL (et non OFF). Avec journal_mode=MEMORY
            # on garde une perf très proche d'OFF sans risque de corruption
            # silencieuse en cas de crash process pendant le build.
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA journal_mode = MEMORY")
            conn.execute("PRAGMA temp_store = MEMORY")
        return conn

    # ----- API publique -----

    def build(
        self,
        source_id: str | None = None,
        *,
        optimize: bool = False,
    ) -> BuildStats:
        """Reconstruit la base. Si `source_id` est `None`, toutes les sources.

        Atomique : écrit dans `<db>.tmp`, puis `os.replace`.

        Args:
            source_id : slug à filtrer, ou ``None`` pour toutes.
            optimize  : si vrai, exécute ``INSERT INTO items_fts(items_fts)
                        VALUES('optimize')`` post-build (compaction FTS5).
        """
        # FTS5 disponible ? Si non, on échoue immédiatement avec un message
        # actionnable (CR senior C2).
        check_fts5_available()

        t0 = time.perf_counter()
        self._errors = []
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.db_path.with_suffix(self.db_path.suffix + ".tmp")
        # Nettoyage d'un tmp orphelin (rebuild précédent crashé).
        if tmp_path.exists():
            tmp_path.unlink()

        conn = self._open_rw(tmp_path, fast=True)
        try:
            drop_schema(conn)
            create_schema(conn)

            n_items = self._load_items(conn, source_id)
            n_episodes = self._load_episodes(conn, source_id)
            n_mentions = self._load_mentions(conn, source_id)
            n_fts = self._populate_fts(conn)
            self._write_meta(conn, source_id=source_id)
            conn.commit()

            if optimize:
                conn.execute(
                    "INSERT INTO items_fts(items_fts) VALUES('optimize')"
                )
                conn.execute(
                    "INSERT INTO episodes_fts(episodes_fts) VALUES('optimize')"
                )
                conn.commit()
        finally:
            conn.close()

        # Atomic swap. Sur Windows, replace remplace même si la cible existe.
        os.replace(tmp_path, self.db_path)

        return BuildStats(
            n_items=n_items,
            n_mentions=n_mentions,
            n_episodes=n_episodes,
            n_fts_rows=n_fts,
            duration_s=time.perf_counter() - t0,
        )

    @property
    def last_errors(self) -> list[str]:
        """Erreurs non-fatales du dernier build (JSON malformés ignorés)."""
        return list(self._errors)

    # ----- Refresh incrémental (read-through) -----

    def refresh_item_file(self, source_id: str, item_id: str, json_path: Path) -> None:
        """Recharge un seul item depuis le fichier (utilisé par read-through).

        Ne touche pas FTS5 — pour un seul item, on supprime+réinsère également
        la ligne dans `items_fts` afin de garder la cohérence de la recherche.
        """
        conn = self._open_rw(self.db_path, fast=False)
        try:
            data = self.loader.read(json_path)
            mtime = self.loader.mtime(json_path)
            self._upsert_item(conn, source_id, data, json_path, mtime)
            self._refresh_item_fts(conn, source_id, item_id)
            conn.commit()
        finally:
            conn.close()

    # ----- Internals -----

    def _load_items(self, conn: sqlite3.Connection, source_id: str | None) -> int:
        rows: list[tuple[Any, ...]] = []
        for src_dir, src_id in self._iter_source_dirs(self.items_dir, source_id):
            for path in self.loader.iter_files(src_dir):
                try:
                    data = self.loader.read(path)
                    rows.append(self._item_to_row(src_id, data, path))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    self._errors.append(f"items:{path}: {exc}")
                    self._warn("Skip item JSON invalide %s: %s", path, exc)
        if rows:
            conn.executemany(
                """
                INSERT INTO items
                  (source_id, id, schema_version, title, types, canonical_key,
                   external_ids, enrichment_suspect, json_path, json_mtime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def _load_episodes(
        self, conn: sqlite3.Connection, source_id: str | None
    ) -> int:
        rows: list[tuple[Any, ...]] = []
        for src_dir, src_id in self._iter_source_dirs(self.episodes_dir, source_id):
            for path in self.loader.iter_files(src_dir):
                try:
                    data = self.loader.read(path)
                    rows.append(self._episode_to_row(src_id, data, path))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    self._errors.append(f"episodes:{path}: {exc}")
                    self._warn(
                        "Skip episode JSON invalide %s: %s", path, exc
                    )
        if rows:
            conn.executemany(
                """
                INSERT INTO episodes
                  (source_id, guid, schema_version, title, hosts, guests,
                   guests_parsed, match_suspect, json_path, json_mtime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def _load_mentions(
        self, conn: sqlite3.Connection, source_id: str | None
    ) -> int:
        rows: list[tuple[Any, ...]] = []
        for src_dir, src_id in self._iter_source_dirs(self.mentions_dir, source_id):
            for path in self.loader.iter_files(src_dir):
                try:
                    data = self.loader.read(path)
                    rows.append(self._mention_to_row(src_id, data, path))
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    self._errors.append(f"mentions:{path}: {exc}")
                    self._warn(
                        "Skip mention JSON invalide %s: %s", path, exc
                    )
        if rows:
            conn.executemany(
                """
                INSERT INTO mentions
                  (source_id, id, schema_version, item_id, episode_guid,
                   timestamp_seconds, recommended_by, recommended_by_norm,
                   quote, json_path, json_mtime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def _iter_source_dirs(
        self, root: Path, source_id: str | None
    ) -> Iterable[tuple[Path, str]]:
        """Yield (subdir, source_id) pour chaque source ou la source filtrée."""
        if not root.exists():
            return
        if source_id is not None:
            sub = root / source_id
            if sub.is_dir():
                yield sub, source_id
            return
        for sub in sorted(root.iterdir()):
            if not sub.is_dir():
                continue
            # On ignore les dossiers de fixtures internes (préfixe __).
            if sub.name.startswith("__"):
                self._warn("Skip source réservée %s", sub.name)
                continue
            yield sub, sub.name

    def _item_to_row(
        self, source_id: str, data: dict[str, Any], path: Path
    ) -> tuple[Any, ...]:
        return (
            source_id,
            str(data["id"]),
            int(data.get("schemaVersion", 1)),
            str(data.get("title", "")),
            _json_dump(data.get("types", [])),
            data.get("canonicalKey"),
            _json_dump(data["externalIds"]) if "externalIds" in data else None,
            1 if data.get("enrichmentSuspect") else 0,
            str(path),
            self.loader.mtime(path),
        )

    def _episode_to_row(
        self, source_id: str, data: dict[str, Any], path: Path
    ) -> tuple[Any, ...]:
        return (
            source_id,
            str(data["guid"]),
            int(data.get("schemaVersion", 1)),
            data.get("title"),
            _json_dump(data.get("hosts", [])),
            _json_dump(data.get("guests", [])),
            _json_dump(data.get("guestsParsed", [])),
            1 if data.get("matchSuspect") else 0,
            str(path),
            self.loader.mtime(path),
        )

    def _mention_to_row(
        self, source_id: str, data: dict[str, Any], path: Path
    ) -> tuple[Any, ...]:
        source_ref = data.get("sourceRef") or {}
        ts_seconds = _parse_timestamp_to_seconds(source_ref.get("timestamp"))
        rec_by = data.get("recommendedBy")
        return (
            source_id,
            str(data["id"]),
            int(data.get("schemaVersion", 1)),
            str(data["itemId"]),
            str(source_ref.get("episodeGuid", "")),
            ts_seconds,
            rec_by,
            _normalize_recommended_by(rec_by),
            data.get("quote"),
            str(path),
            self.loader.mtime(path),
        )

    def _upsert_item(
        self,
        conn: sqlite3.Connection,
        source_id: str,
        data: dict[str, Any],
        path: Path,
        mtime: float,
    ) -> None:
        # Vrai upsert ON CONFLICT : préserve les FK (mentions référençant cet item).
        # DELETE+INSERT casserait `PRAGMA foreign_keys=ON` (Fixer P2.8 C3).
        conn.execute(
            """
            INSERT INTO items
              (source_id, id, schema_version, title, types, canonical_key,
               external_ids, enrichment_suspect, json_path, json_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, id) DO UPDATE SET
              schema_version=excluded.schema_version,
              title=excluded.title,
              types=excluded.types,
              canonical_key=excluded.canonical_key,
              external_ids=excluded.external_ids,
              enrichment_suspect=excluded.enrichment_suspect,
              json_path=excluded.json_path,
              json_mtime=excluded.json_mtime
            """,
            (
                source_id,
                str(data["id"]),
                int(data.get("schemaVersion", 1)),
                str(data.get("title", "")),
                _json_dump(data.get("types", [])),
                data.get("canonicalKey"),
                _json_dump(data["externalIds"]) if "externalIds" in data else None,
                1 if data.get("enrichmentSuspect") else 0,
                str(path),
                mtime,
            ),
        )

    def _populate_fts(self, conn: sqlite3.Connection) -> int:
        """Remplit items_fts + episodes_fts.

        Stratégie (CR archi P1-3) : un SELECT joint avec sous-requêtes
        agrégées sur des jointures indexées. Les ``guests_parsed`` étant
        stockés en JSON liste (``[...]``), on les parse côté SQL via
        ``json_each`` pour stocker du texte propre dans ``items_fts``
        (CR senior H4/H5).
        """
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO items_fts (source_id, id, title, recommended_by, guests_text)
            SELECT
              i.source_id,
              i.id,
              i.title,
              COALESCE((
                SELECT GROUP_CONCAT(DISTINCT m.recommended_by_norm)
                FROM mentions m
                WHERE m.source_id = i.source_id AND m.item_id = i.id
                  AND m.recommended_by_norm IS NOT NULL
              ), ''),
              COALESCE((
                SELECT GROUP_CONCAT(DISTINCT g.value)
                FROM mentions m
                JOIN episodes e
                  ON e.source_id = m.source_id AND e.guid = m.episode_guid
                JOIN json_each(e.guests_parsed) g
                WHERE m.source_id = i.source_id AND m.item_id = i.id
              ), '')
            FROM items i
            """
        )
        n_items_fts = cur.rowcount

        cur.execute(
            """
            INSERT INTO episodes_fts (source_id, guid, title, hosts_text, guests_text)
            SELECT
              e.source_id,
              e.guid,
              COALESCE(e.title, ''),
              COALESCE((
                SELECT GROUP_CONCAT(h.value, ' ')
                FROM json_each(e.hosts) h
              ), ''),
              COALESCE((
                SELECT GROUP_CONCAT(g.value, ' ')
                FROM json_each(e.guests_parsed) g
              ), '')
            FROM episodes e
            """
        )
        n_eps_fts = cur.rowcount
        return int(n_items_fts) + int(n_eps_fts)

    def _refresh_item_fts(
        self, conn: sqlite3.Connection, source_id: str, item_id: str
    ) -> None:
        """Supprime+ré-insère la ligne items_fts pour un item donné."""
        conn.execute(
            "DELETE FROM items_fts WHERE source_id = ? AND id = ?",
            (source_id, item_id),
        )
        # SQLite : GROUP_CONCAT(DISTINCT x) ne tolère qu'UN argument (pas de séparateur).
        # On garde la virgule par défaut ; FTS5 tokenize sur la virgule.
        conn.execute(
            """
            INSERT INTO items_fts (source_id, id, title, recommended_by, guests_text)
            SELECT
              i.source_id, i.id, i.title,
              COALESCE((SELECT GROUP_CONCAT(DISTINCT m.recommended_by_norm)
                        FROM mentions m
                        WHERE m.source_id = i.source_id AND m.item_id = i.id
                          AND m.recommended_by_norm IS NOT NULL), ''),
              COALESCE((SELECT GROUP_CONCAT(DISTINCT g.value)
                        FROM mentions m
                        JOIN episodes e
                          ON e.source_id = m.source_id AND e.guid = m.episode_guid
                        JOIN json_each(e.guests_parsed) g
                        WHERE m.source_id = i.source_id AND m.item_id = i.id), '')
            FROM items i
            WHERE i.source_id = ? AND i.id = ?
            """,
            (source_id, item_id),
        )

    def _write_meta(
        self, conn: sqlite3.Connection, *, source_id: str | None
    ) -> None:
        now_iso = datetime.now(UTC).isoformat(timespec="seconds")
        built_for = (
            json.dumps(["*"]) if source_id is None else json.dumps([source_id])
        )
        git_sha = _try_git_sha() or ""
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO cache_meta (key, value) VALUES (?, ?)",
            [
                ("cache_schema_version", str(CACHE_SCHEMA_VERSION)),
                ("built_at", now_iso),
                ("built_by", _BUILDER_TAG),
                ("built_for_sources", built_for),
                ("git_sha", git_sha),
            ],
        )

    def vacuum(self) -> None:
        """VACUUM la base (post-build optionnel — compaction)."""
        # VACUUM ne tolère pas de transaction ouverte ; on ouvre une
        # connexion neuve sans pragmas spéciaux (FK ON n'empêche pas
        # VACUUM mais reste cohérent).
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("VACUUM")
        finally:
            conn.close()
