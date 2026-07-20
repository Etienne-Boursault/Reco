"""tests pour embeddings.recommend + search.similarity (façade)."""
from __future__ import annotations

import numpy as np

from embeddings.recommend import Recommendation, SimilarityRecommender
from embeddings.store import EmbeddingStore
from search.similarity import (
    DEFAULT_DEDUP_THRESHOLD,
    DEFAULT_TOP_K,
    SemanticHit,
    SemanticSearchService,
)


def _seed(store: EmbeddingStore) -> None:
    """3 items : a ~ b (proches), c orthogonal."""
    store.upsert(
        source_id="s", id="a", model="m", dim=2,
        vector=np.array([1.0, 0.0], dtype=np.float32),
        source_hash="h", embedded_at="t",
    )
    store.upsert(
        source_id="s", id="b", model="m", dim=2,
        vector=np.array([0.99, 0.01], dtype=np.float32),
        source_hash="h", embedded_at="t",
    )
    store.upsert(
        source_id="s", id="c", model="m", dim=2,
        vector=np.array([0.0, 1.0], dtype=np.float32),
        source_hash="h", embedded_at="t",
    )


def test_top_k_basic(tmp_store: EmbeddingStore) -> None:
    _seed(tmp_store)
    out = SimilarityRecommender(tmp_store).top_k("s", "a", k=5)
    assert [r.item_id for r in out] == ["b", "c"]
    assert isinstance(out[0], Recommendation)
    assert out[0].score > out[1].score


def test_top_k_filters_self(tmp_store: EmbeddingStore) -> None:
    _seed(tmp_store)
    out = SimilarityRecommender(tmp_store).top_k("s", "a", k=10)
    assert "a" not in {r.item_id for r in out}


def test_top_k_unknown_item_returns_empty(tmp_store: EmbeddingStore) -> None:
    _seed(tmp_store)
    out = SimilarityRecommender(tmp_store).top_k("s", "ghost", k=5)
    assert out == []


def test_top_k_zero_k_returns_empty(tmp_store: EmbeddingStore) -> None:
    _seed(tmp_store)
    out = SimilarityRecommender(tmp_store).top_k("s", "a", k=0)
    assert out == []


def test_top_k_exclude_ids(tmp_store: EmbeddingStore) -> None:
    _seed(tmp_store)
    out = SimilarityRecommender(tmp_store).top_k(
        "s", "a", k=5, exclude_ids=frozenset({"b"})
    )
    assert [r.item_id for r in out] == ["c"]


def test_top_k_min_score(tmp_store: EmbeddingStore) -> None:
    _seed(tmp_store)
    out = SimilarityRecommender(tmp_store).top_k("s", "a", k=5, min_score=0.5)
    assert {r.item_id for r in out} == {"b"}


def test_top_k_model_filter_excludes_other_dim(tmp_store: EmbeddingStore) -> None:
    """Filtre par dim implicite (mismatch ignoré, pas d'exception)."""
    _seed(tmp_store)
    # Ajoute un item dans une autre dim ; il doit être ignoré.
    tmp_store.upsert(
        source_id="s", id="bigdim", model="m2", dim=4,
        vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        source_hash="h", embedded_at="t",
    )
    out = SimilarityRecommender(tmp_store).top_k("s", "a", k=10)
    assert "bigdim" not in {r.item_id for r in out}


def test_top_k_empty_source(tmp_store: EmbeddingStore) -> None:
    out = SimilarityRecommender(tmp_store).top_k("vide", "any", k=3)
    assert out == []


def test_top_k_no_other_items_returns_empty(tmp_path) -> None:
    """item présent mais aucun autre dans le store."""
    store = EmbeddingStore(tmp_path / "lone.sqlite")
    try:
        store.upsert(
            source_id="s", id="solo", model="m", dim=2,
            vector=np.array([1.0, 0.0], dtype=np.float32),
            source_hash="h", embedded_at="t",
        )
        # Filtrer par un modèle inexistant → iter_source retourne juste l'item solo,
        # qui sera filtré par exclude_ids={solo} -> retour vide.
        out = SimilarityRecommender(store).top_k("s", "solo", k=5, model="other")
        assert out == []
    finally:
        store.close()


# ------- Façade search.similarity -----------------------------------------


def test_semantic_search_service_similar_items(tmp_store: EmbeddingStore) -> None:
    _seed(tmp_store)
    svc = SemanticSearchService(tmp_store)
    hits = svc.similar_items("s", "a", k=5)
    assert all(isinstance(h, SemanticHit) for h in hits)
    assert [h.id for h in hits] == ["b", "c"]
    assert hits[0].source_id == "s"


def test_semantic_search_service_dedup_pairs(tmp_store: EmbeddingStore) -> None:
    _seed(tmp_store)
    svc = SemanticSearchService(tmp_store)
    pairs = svc.dedup_pairs("s", threshold=0.85)
    assert len(pairs) == 1
    assert {pairs[0].a, pairs[0].b} == {"a", "b"}


def test_defaults() -> None:
    assert DEFAULT_TOP_K == 10
    assert DEFAULT_DEDUP_THRESHOLD == 0.85
