"""tests pour embeddings.dedup."""
from __future__ import annotations

import numpy as np
import pytest

from embeddings.dedup import CrossEpisodeDedup, DedupPair
from embeddings.store import EmbeddingStore


def _store_with(rows: list[tuple[str, str, np.ndarray, str]], tmp_path) -> EmbeddingStore:
    """Helper : (source_id, id, vector, model)."""
    store = EmbeddingStore(tmp_path / "d.sqlite")
    for sid, iid, v, model in rows:
        store.upsert(
            source_id=sid, id=iid, model=model, dim=v.size, vector=v,
            source_hash=f"h-{iid}", embedded_at="t",
        )
    return store


def test_suggest_finds_high_sim_pair(tmp_path) -> None:
    v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([0.99, 0.01, 0.0], dtype=np.float32)  # ~1.0 cosine avec v1
    v3 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    store = _store_with(
        [
            ("s", "tombeau", v1, "m"),
            ("s", "grave", v2, "m"),
            ("s", "autre", v3, "m"),
        ],
        tmp_path,
    )
    try:
        pairs = CrossEpisodeDedup(store).suggest("s", threshold=0.85)
        assert len(pairs) == 1
        p = pairs[0]
        assert p.a == "grave" and p.b == "tombeau"  # tri lex
        assert p.score > 0.85
        assert p.source_id == "s"
    finally:
        store.close()


def test_suggest_empty_below_threshold(tmp_path) -> None:
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0], dtype=np.float32)
    store = _store_with([("s", "a", v1, "m"), ("s", "b", v2, "m")], tmp_path)
    try:
        assert CrossEpisodeDedup(store).suggest("s", threshold=0.5) == []
    finally:
        store.close()


def test_suggest_returns_empty_when_lt_2_items(tmp_path) -> None:
    store = EmbeddingStore(tmp_path / "x.sqlite")
    try:
        assert CrossEpisodeDedup(store).suggest("s") == []
        store.upsert(
            source_id="s", id="solo", model="m", dim=2,
            vector=np.array([1.0, 0.0], dtype=np.float32),
            source_hash="h", embedded_at="t",
        )
        assert CrossEpisodeDedup(store).suggest("s") == []
    finally:
        store.close()


def test_suggest_validates_threshold(tmp_path) -> None:
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    store = _store_with([("s", "a", v1, "m"), ("s", "b", v1, "m")], tmp_path)
    try:
        with pytest.raises(ValueError, match="threshold"):
            CrossEpisodeDedup(store).suggest("s", threshold=1.5)
    finally:
        store.close()


def test_suggest_detects_dim_mismatch(tmp_path) -> None:
    store = EmbeddingStore(tmp_path / "mm.sqlite")
    try:
        store.upsert(
            source_id="s", id="a", model="m1", dim=2,
            vector=np.array([1.0, 0.0], dtype=np.float32),
            source_hash="h", embedded_at="t",
        )
        store.upsert(
            source_id="s", id="b", model="m2", dim=3,
            vector=np.array([1.0, 0.0, 0.0], dtype=np.float32),
            source_hash="h", embedded_at="t",
        )
        with pytest.raises(ValueError, match="dimension mismatch"):
            CrossEpisodeDedup(store).suggest("s")
    finally:
        store.close()


def test_suggest_filters_by_model(tmp_path) -> None:
    v = np.array([1.0, 0.0], dtype=np.float32)
    store = EmbeddingStore(tmp_path / "f.sqlite")
    try:
        store.upsert(
            source_id="s", id="a", model="m1", dim=2, vector=v,
            source_hash="h", embedded_at="t",
        )
        store.upsert(
            source_id="s", id="b", model="m2", dim=2, vector=v,
            source_hash="h", embedded_at="t",
        )
        store.upsert(
            source_id="s", id="c", model="m1", dim=2,
            vector=np.array([0.99, 0.01], dtype=np.float32),
            source_hash="h", embedded_at="t",
        )
        pairs = CrossEpisodeDedup(store).suggest("s", model="m1", threshold=0.9)
        assert {p.a for p in pairs} | {p.b for p in pairs} == {"a", "c"}
    finally:
        store.close()


def test_suggest_max_pairs_caps(tmp_path) -> None:
    base = np.array([1.0, 0.0], dtype=np.float32)
    rows = [("s", chr(ord("a") + i), base, "m") for i in range(5)]
    store = _store_with(rows, tmp_path)
    try:
        pairs = CrossEpisodeDedup(store).suggest("s", threshold=0.5, max_pairs=3)
        assert len(pairs) == 3
    finally:
        store.close()


def test_dedup_pair_to_dict_with_titles() -> None:
    p = DedupPair(source_id="s", a="x", b="y", score=0.9123456)
    d = p.to_dict(titles={"x": "X title", "y": "Y title"})
    assert d == {
        "a": "x",
        "b": "y",
        "score": 0.9123,
        "titles": ["X title", "Y title"],
    }


def test_dedup_pair_to_dict_without_titles() -> None:
    p = DedupPair(source_id="s", a="x", b="y", score=0.91)
    d = p.to_dict()
    assert "titles" not in d
    assert d["a"] == "x" and d["b"] == "y"


def test_suggest_unordered_max_pairs_none(tmp_path) -> None:
    v = np.array([1.0, 0.0], dtype=np.float32)
    store = _store_with([("s", "a", v, "m"), ("s", "b", v, "m")], tmp_path)
    try:
        pairs = CrossEpisodeDedup(store).suggest("s", threshold=0.5, max_pairs=None)
        assert len(pairs) == 1
    finally:
        store.close()
