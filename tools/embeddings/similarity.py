"""embeddings.similarity — Cosine similarity + top-K.

Implémentations *pures* (numpy) ; aucune dépendance au store ni à
l'encoder. Réutilisables côté CLI et tests.

Choix :
  * Matrice normalisée à la volée (``X / ||X||``) — overhead négligeable
    sur < 10k vecteurs, et évite de stocker la norme côté store.
  * Vecteur nul → similarity 0 (par convention, plutôt qu'un NaN).
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-12


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Similarité cosinus entre deux vecteurs 1-D.

    Conventions :
      * Si l'un des vecteurs est nul → 0.0 (pas de division par zéro).
      * ``a.shape != b.shape`` → ``ValueError`` (dim mismatch).
      * Retour borné dans ``[-1.0, 1.0]`` (clip pour éviter les erreurs
        flottantes qui donneraient 1.0000001).
    """
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")
    if a.ndim != 1:
        raise ValueError(f"expected 1-D vectors, got ndim={a.ndim}")
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < _EPS or nb < _EPS:
        return 0.0
    score = float(np.dot(a, b) / (na * nb))
    if score > 1.0:
        return 1.0
    if score < -1.0:  # pragma: no cover - rare float underflow
        return -1.0
    return score


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise chaque ligne. Les lignes nulles restent nulles."""
    if matrix.ndim != 2:
        raise ValueError(f"expected 2-D matrix, got ndim={matrix.ndim}")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe = np.where(norms < _EPS, 1.0, norms)
    out = matrix / safe
    # Les lignes nulles → on remet à 0 (sinon division par 1 garde 0).
    return out


def top_k(
    query: np.ndarray,
    ids: list[str],
    matrix: np.ndarray,
    *,
    k: int = 10,
    exclude_ids: frozenset[str] | None = None,
    min_score: float = -1.0,
) -> list[tuple[str, float]]:
    """Renvoie les top-K voisins de ``query`` dans ``matrix``.

    Args:
      query       : vecteur (dim,).
      ids         : ids alignés sur ``matrix.shape[0]``.
      matrix      : (N, dim).
      k           : nombre max de voisins.
      exclude_ids : ids à filtrer (typiquement le self-id).
      min_score   : seuil inclus — pas de voisin sous ce seuil.

    Tri stable décroissant. Retour : ``[(id, score), ...]``.
    """
    if matrix.ndim != 2:
        raise ValueError(f"matrix must be 2-D, got ndim={matrix.ndim}")
    if query.ndim != 1:
        raise ValueError(f"query must be 1-D, got ndim={query.ndim}")
    n = matrix.shape[0]
    if n == 0 or k <= 0:
        return []
    if len(ids) != n:
        raise ValueError(f"ids len {len(ids)} ≠ matrix rows {n}")
    if query.shape[0] != matrix.shape[1]:
        raise ValueError(
            f"query dim {query.shape[0]} ≠ matrix dim {matrix.shape[1]}"
        )

    qn = float(np.linalg.norm(query))
    if qn < _EPS:
        return []
    q_normed = query / qn
    norms = np.linalg.norm(matrix, axis=1)
    safe_norms = np.where(norms < _EPS, 1.0, norms)
    m_normed = matrix / safe_norms[:, None]
    # Lignes nulles -> score 0 (overrides mask).
    null_mask = norms < _EPS
    scores = m_normed @ q_normed
    scores = np.where(null_mask, -np.inf, scores)

    excluded = exclude_ids or frozenset()
    # On collecte tous les candidats valides, puis sort.
    candidates: list[tuple[str, float]] = []
    for idx, item_id in enumerate(ids):
        if item_id in excluded:
            continue
        s = float(scores[idx])
        if s == float("-inf"):
            continue
        if s < min_score:
            continue
        candidates.append((item_id, s))

    # Tri décroissant (score), tie-break par id pour stabilité.
    candidates.sort(key=lambda kv: (-kv[1], kv[0]))
    return candidates[:k]
