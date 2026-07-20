"""tests pour embeddings.similarity."""
from __future__ import annotations

import numpy as np
import pytest

from embeddings.similarity import cosine_similarity, normalize_rows, top_k


def test_cosine_identical() -> None:
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal() -> None:
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_opposite() -> None:
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([-1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_zero_vector() -> None:
    z = np.zeros(3, dtype=np.float32)
    v = np.array([1.0, 1.0, 1.0], dtype=np.float32)
    assert cosine_similarity(z, v) == 0.0
    assert cosine_similarity(v, z) == 0.0


def test_cosine_clips_overshoot() -> None:
    # Simule un cas flottant où le produit > 1 (force-feed via vecteur unitaire).
    v = np.array([1.0, 1.0], dtype=np.float32)
    score = cosine_similarity(v, v)
    assert -1.0 <= score <= 1.0


def test_cosine_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        cosine_similarity(np.zeros(3, dtype=np.float32), np.zeros(4, dtype=np.float32))


def test_cosine_rejects_non_1d() -> None:
    with pytest.raises(ValueError, match="1-D"):
        cosine_similarity(np.zeros((2, 2), dtype=np.float32), np.zeros((2, 2), dtype=np.float32))


def test_normalize_rows() -> None:
    m = np.array([[3.0, 4.0], [0.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    out = normalize_rows(m)
    np.testing.assert_allclose(out[0], [0.6, 0.8], atol=1e-6)
    np.testing.assert_allclose(out[1], [0.0, 0.0])
    np.testing.assert_allclose(out[2], [1.0, 0.0])


def test_normalize_rows_rejects_non_2d() -> None:
    with pytest.raises(ValueError, match="2-D"):
        normalize_rows(np.zeros(3, dtype=np.float32))


def test_top_k_basic() -> None:
    q = np.array([1.0, 0.0], dtype=np.float32)
    ids = ["a", "b", "c"]
    matrix = np.array([[1.0, 0.0], [0.5, 0.5], [-1.0, 0.0]], dtype=np.float32)
    out = top_k(q, ids, matrix, k=2)
    assert out[0][0] == "a"
    assert out[0][1] == pytest.approx(1.0)
    assert out[1][0] == "b"
    assert out[1][1] == pytest.approx(0.7071, abs=1e-3)


def test_top_k_excludes_self() -> None:
    q = np.array([1.0, 0.0], dtype=np.float32)
    ids = ["self", "b"]
    matrix = np.array([[1.0, 0.0], [0.5, 0.5]], dtype=np.float32)
    out = top_k(q, ids, matrix, k=5, exclude_ids=frozenset({"self"}))
    assert [o[0] for o in out] == ["b"]


def test_top_k_min_score_filter() -> None:
    q = np.array([1.0, 0.0], dtype=np.float32)
    ids = ["a", "b"]
    matrix = np.array([[1.0, 0.0], [-1.0, 0.0]], dtype=np.float32)
    out = top_k(q, ids, matrix, k=5, min_score=0.5)
    assert [o[0] for o in out] == ["a"]


def test_top_k_zero_query_returns_empty() -> None:
    q = np.zeros(3, dtype=np.float32)
    out = top_k(q, ["a"], np.array([[1.0, 0.0, 0.0]], dtype=np.float32), k=5)
    assert out == []


def test_top_k_empty_matrix() -> None:
    q = np.array([1.0], dtype=np.float32)
    out = top_k(q, [], np.zeros((0, 1), dtype=np.float32), k=5)
    assert out == []


def test_top_k_k_zero_or_negative() -> None:
    q = np.array([1.0], dtype=np.float32)
    matrix = np.array([[1.0]], dtype=np.float32)
    assert top_k(q, ["a"], matrix, k=0) == []
    assert top_k(q, ["a"], matrix, k=-3) == []


def test_top_k_ignores_null_rows() -> None:
    q = np.array([1.0, 0.0], dtype=np.float32)
    ids = ["zero", "good"]
    matrix = np.array([[0.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    out = top_k(q, ids, matrix, k=5)
    assert [o[0] for o in out] == ["good"]


def test_top_k_dim_mismatch() -> None:
    with pytest.raises(ValueError, match="dim"):
        top_k(
            np.array([1.0, 0.0], dtype=np.float32),
            ["a"],
            np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
            k=1,
        )


def test_top_k_ids_len_mismatch() -> None:
    with pytest.raises(ValueError, match="ids len"):
        top_k(
            np.array([1.0], dtype=np.float32),
            ["a", "b"],
            np.array([[1.0]], dtype=np.float32),
            k=1,
        )


def test_top_k_matrix_must_be_2d() -> None:
    with pytest.raises(ValueError, match="2-D"):
        top_k(
            np.array([1.0], dtype=np.float32),
            ["a"],
            np.array([1.0], dtype=np.float32),
            k=1,
        )


def test_top_k_query_must_be_1d() -> None:
    with pytest.raises(ValueError, match="1-D"):
        top_k(
            np.array([[1.0]], dtype=np.float32),
            ["a"],
            np.array([[1.0]], dtype=np.float32),
            k=1,
        )


def test_top_k_tie_break_by_id() -> None:
    q = np.array([1.0, 0.0], dtype=np.float32)
    ids = ["zeta", "alpha", "beta"]
    matrix = np.tile([1.0, 0.0], (3, 1)).astype(np.float32)
    out = top_k(q, ids, matrix, k=3)
    assert [o[0] for o in out] == ["alpha", "beta", "zeta"]
