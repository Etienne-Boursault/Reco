"""embeddings.store — Persistance SQLite des embeddings.

Table sœur du cache items/mentions (ADR 0020 § P2-7) — *séparée* du cache
FTS5 pour découpler le cycle de vie (rebuild cache ≠ ré-embed). PK
composite ``(source_id, id)``.

Schéma v1 (ADR 0033) :

.. code-block:: sql

   CREATE TABLE items_embeddings (
     source_id   TEXT NOT NULL,
     id          TEXT NOT NULL,
     model       TEXT NOT NULL,
     dim         INTEGER NOT NULL,
     vector      BLOB NOT NULL,   -- numpy float32 packed (little-endian)
     embedded_at TEXT NOT NULL,
     source_hash TEXT NOT NULL,
     PRIMARY KEY (source_id, id)
   );
   CREATE INDEX idx_embeddings_model ON items_embeddings(model);

Le vecteur est sérialisé via ``ndarray.tobytes()`` ; on stocke ``dim``
en colonne pour permettre la re-lecture sans information externe (utile
pour des dumps offline).
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Final, Iterator

import numpy as np

from embeddings.ports import StoredEmbedding

EMBEDDINGS_SCHEMA_VERSION: Final[int] = 1

_CREATE_TABLE: Final[str] = """
CREATE TABLE IF NOT EXISTS items_embeddings (
  source_id   TEXT NOT NULL,
  id          TEXT NOT NULL,
  model       TEXT NOT NULL,
  dim         INTEGER NOT NULL,
  vector      BLOB NOT NULL,
  embedded_at TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  PRIMARY KEY (source_id, id)
)
"""

_CREATE_META: Final[str] = """
CREATE TABLE IF NOT EXISTS embeddings_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
)
"""

_CREATE_IDX_MODEL: Final[str] = (
    "CREATE INDEX IF NOT EXISTS idx_embeddings_model "
    "ON items_embeddings(model)"
)


class EmbeddingStore:
    """Store RW SQLite. Crée le fichier si absent.

    H15-2 — `sqlite3.Connection` est thread-safe au niveau driver (Python
    > 3.11) MAIS ``check_same_thread=False`` ouvre la porte aux courses sur
    ``execute``/``commit`` entrelacés depuis plusieurs threads. On
    sérialise les accès via un ``threading.RLock`` interne. Coût négligeable
    en mono-thread (re-entrant ⇒ pas de deadlock sur ``upsert`` →
    ``_pack``). Garde la propriété WAL pour les lecteurs concurrents.
    """

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        # Pragmas raisonnables pour des écritures groupées.
        with self._lock:
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        self.init_schema()

    # ----- Schema -----

    def init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(_CREATE_TABLE)
            cur.execute(_CREATE_META)
            cur.execute(_CREATE_IDX_MODEL)
            cur.execute(
                "INSERT OR REPLACE INTO embeddings_meta(key, value) VALUES(?, ?)",
                ("embeddings_schema_version", str(EMBEDDINGS_SCHEMA_VERSION)),
            )
            self._conn.commit()

    # ----- Encoding helpers -----

    @staticmethod
    def _pack(vector: np.ndarray) -> bytes:
        v = np.ascontiguousarray(vector, dtype=np.float32)
        return v.tobytes()

    @staticmethod
    def _unpack(blob: bytes, dim: int) -> np.ndarray:
        arr = np.frombuffer(blob, dtype=np.float32)
        if arr.size != dim:
            raise ValueError(
                f"vector size {arr.size} ≠ dim {dim} — store corrompu ?"
            )
        # Copy() pour casser le read-only flag de frombuffer.
        return arr.copy()

    # ----- CRUD -----

    def upsert(
        self,
        *,
        source_id: str,
        id: str,
        model: str,
        dim: int,
        vector: np.ndarray,
        source_hash: str,
        embedded_at: str,
    ) -> None:
        if vector.ndim != 1:
            raise ValueError(f"vector must be 1-D, got shape {vector.shape}")
        if int(vector.size) != int(dim):
            raise ValueError(
                f"vector size {vector.size} ≠ dim {dim} (item={source_id}/{id})"
            )
        blob = self._pack(vector)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO items_embeddings "
                "(source_id, id, model, dim, vector, embedded_at, source_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source_id, id, model, int(dim), blob, embedded_at, source_hash),
            )
            self._conn.commit()

    def upsert_batch(
        self,
        rows: list[StoredEmbedding],
    ) -> int:
        """Insert/update en batch. Renvoie le nombre de lignes écrites."""
        if not rows:
            return 0
        payload = [
            (
                r.source_id,
                r.id,
                r.model,
                int(r.dim),
                self._pack(r.vector),
                r.embedded_at,
                r.source_hash,
            )
            for r in rows
        ]
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO items_embeddings "
                "(source_id, id, model, dim, vector, embedded_at, source_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                payload,
            )
            self._conn.commit()
        return len(payload)

    def get(self, source_id: str, item_id: str) -> StoredEmbedding | None:
        cur = self._conn.execute(
            "SELECT * FROM items_embeddings WHERE source_id = ? AND id = ?",
            (source_id, item_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_obj(row)

    def get_source_hash(self, source_id: str, item_id: str) -> str | None:
        cur = self._conn.execute(
            "SELECT source_hash FROM items_embeddings "
            "WHERE source_id = ? AND id = ?",
            (source_id, item_id),
        )
        row = cur.fetchone()
        return row["source_hash"] if row else None

    def iter_source(
        self, source_id: str, *, model: str | None = None
    ) -> Iterator[StoredEmbedding]:
        if model is None:
            cur = self._conn.execute(
                "SELECT * FROM items_embeddings WHERE source_id = ? ORDER BY id",
                (source_id,),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM items_embeddings "
                "WHERE source_id = ? AND model = ? ORDER BY id",
                (source_id, model),
            )
        for row in cur:
            yield self._row_to_obj(row)

    def count(self, source_id: str | None = None) -> int:
        if source_id is None:
            cur = self._conn.execute("SELECT COUNT(*) AS n FROM items_embeddings")
        else:
            cur = self._conn.execute(
                "SELECT COUNT(*) AS n FROM items_embeddings WHERE source_id = ?",
                (source_id,),
            )
        return int(cur.fetchone()["n"])

    def delete(self, source_id: str, item_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM items_embeddings WHERE source_id = ? AND id = ?",
                (source_id, item_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def _row_to_obj(self, row: sqlite3.Row) -> StoredEmbedding:
        dim = int(row["dim"])
        return StoredEmbedding(
            source_id=row["source_id"],
            id=row["id"],
            model=row["model"],
            dim=dim,
            vector=self._unpack(row["vector"], dim),
            source_hash=row["source_hash"],
            embedded_at=row["embedded_at"],
        )

    # ----- Lifecycle -----

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.ProgrammingError:  # pragma: no cover - idempotence
            pass

    def __enter__(self) -> "EmbeddingStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
