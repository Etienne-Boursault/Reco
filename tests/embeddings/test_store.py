"""tests pour embeddings.store."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from embeddings.ports import StoredEmbedding
from embeddings.store import EMBEDDINGS_SCHEMA_VERSION, EmbeddingStore


def _vec(seed: int, dim: int = 8) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).astype(np.float32)


def test_init_schema_creates_tables(tmp_path: Path) -> None:
    db = tmp_path / "x.sqlite"
    store = EmbeddingStore(db)
    try:
        # Réouvre via raw sqlite pour lister les tables.
        import sqlite3

        conn = sqlite3.connect(str(db))
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        conn.close()
        assert {"items_embeddings", "embeddings_meta"}.issubset(names)
    finally:
        store.close()


def test_upsert_and_get_roundtrip(tmp_store: EmbeddingStore) -> None:
    v = _vec(1)
    tmp_store.upsert(
        source_id="s",
        id="a",
        model="m1",
        dim=v.size,
        vector=v,
        source_hash="h1",
        embedded_at="2026-06-11T00:00:00+00:00",
    )
    got = tmp_store.get("s", "a")
    assert got is not None
    assert got.id == "a"
    assert got.dim == v.size
    np.testing.assert_array_equal(got.vector, v)
    assert got.source_hash == "h1"


def test_get_missing_returns_none(tmp_store: EmbeddingStore) -> None:
    assert tmp_store.get("s", "missing") is None
    assert tmp_store.get_source_hash("s", "missing") is None


def test_upsert_replaces_existing(tmp_store: EmbeddingStore) -> None:
    v1, v2 = _vec(1), _vec(2)
    for v, h in [(v1, "h1"), (v2, "h2")]:
        tmp_store.upsert(
            source_id="s", id="a", model="m", dim=v.size, vector=v,
            source_hash=h, embedded_at="t",
        )
    got = tmp_store.get("s", "a")
    assert got is not None
    np.testing.assert_array_equal(got.vector, v2)
    assert got.source_hash == "h2"


def test_upsert_rejects_dim_mismatch(tmp_store: EmbeddingStore) -> None:
    with pytest.raises(ValueError):
        tmp_store.upsert(
            source_id="s", id="a", model="m", dim=99,
            vector=_vec(1, dim=8), source_hash="h", embedded_at="t",
        )


def test_upsert_rejects_non_1d(tmp_store: EmbeddingStore) -> None:
    with pytest.raises(ValueError):
        tmp_store.upsert(
            source_id="s", id="a", model="m", dim=4,
            vector=np.zeros((2, 2), dtype=np.float32),
            source_hash="h", embedded_at="t",
        )


def test_upsert_batch(tmp_store: EmbeddingStore) -> None:
    rows = [
        StoredEmbedding(
            source_id="s", id=f"i{i}", model="m", dim=8,
            vector=_vec(i), source_hash=f"h{i}", embedded_at="t",
        )
        for i in range(3)
    ]
    assert tmp_store.upsert_batch(rows) == 3
    assert tmp_store.count("s") == 3
    assert tmp_store.count() == 3
    # Batch vide -> no-op.
    assert tmp_store.upsert_batch([]) == 0


def test_iter_source_and_model_filter(tmp_store: EmbeddingStore) -> None:
    tmp_store.upsert(
        source_id="s", id="a", model="m1", dim=8,
        vector=_vec(1), source_hash="h", embedded_at="t",
    )
    tmp_store.upsert(
        source_id="s", id="b", model="m2", dim=8,
        vector=_vec(2), source_hash="h", embedded_at="t",
    )
    ids_all = [r.id for r in tmp_store.iter_source("s")]
    assert ids_all == ["a", "b"]
    ids_m1 = [r.id for r in tmp_store.iter_source("s", model="m1")]
    assert ids_m1 == ["a"]


def test_delete(tmp_store: EmbeddingStore) -> None:
    tmp_store.upsert(
        source_id="s", id="a", model="m", dim=4,
        vector=_vec(1, dim=4), source_hash="h", embedded_at="t",
    )
    assert tmp_store.delete("s", "a") is True
    assert tmp_store.delete("s", "a") is False  # already gone
    assert tmp_store.get("s", "a") is None


def test_get_source_hash(tmp_store: EmbeddingStore) -> None:
    tmp_store.upsert(
        source_id="s", id="a", model="m", dim=4,
        vector=_vec(1, dim=4), source_hash="ABC", embedded_at="t",
    )
    assert tmp_store.get_source_hash("s", "a") == "ABC"


def test_unpack_detects_corruption(tmp_store: EmbeddingStore) -> None:
    """Si dim stockée ne matche pas le blob, on lève à la lecture."""
    tmp_store.upsert(
        source_id="s", id="a", model="m", dim=4,
        vector=_vec(1, dim=4), source_hash="h", embedded_at="t",
    )
    # Corrompt manuellement la colonne dim.
    tmp_store._conn.execute(
        "UPDATE items_embeddings SET dim = 99 WHERE source_id=? AND id=?",
        ("s", "a"),
    )
    tmp_store._conn.commit()
    with pytest.raises(ValueError, match="store corrompu"):
        tmp_store.get("s", "a")


def test_context_manager_closes(tmp_path: Path) -> None:
    db = tmp_path / "ctx.sqlite"
    with EmbeddingStore(db) as store:
        assert store.count() == 0
    # close() doit être idempotent
    store.close()


def test_schema_version_meta(tmp_path: Path) -> None:
    db = tmp_path / "meta.sqlite"
    store = EmbeddingStore(db)
    try:
        row = store._conn.execute(
            "SELECT value FROM embeddings_meta WHERE key='embeddings_schema_version'"
        ).fetchone()
        assert row is not None
        assert int(row["value"]) == EMBEDDINGS_SCHEMA_VERSION
    finally:
        store.close()
