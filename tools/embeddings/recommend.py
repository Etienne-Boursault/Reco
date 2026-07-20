"""embeddings.recommend — Recommandations sémantiques top-K.

API minimale pour le widget "continue le voyage" (Phase 3) et pour
alimenter d'éventuels rerankers ML futurs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from embeddings.ports import EmbeddingStorePort
from embeddings.similarity import top_k


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Item recommandé + score (cosine ∈ [-1, 1])."""

    item_id: str
    score: float


class SimilarityRecommender:
    """Top-K voisins d'un item donné dans la même source.

    Pas (encore) de cross-source — chaque source a son propre corpus.
    Le recommender ne filtre PAS par type/creator par défaut ; ces
    filtres sont externes (le caller passe ``exclude_ids``).
    """

    def __init__(self, store: EmbeddingStorePort) -> None:
        self._store = store

    def top_k(
        self,
        source_id: str,
        item_id: str,
        *,
        k: int = 10,
        model: str | None = None,
        exclude_ids: frozenset[str] | None = None,
        min_score: float = -1.0,
    ) -> list[Recommendation]:
        """Renvoie les K items les plus proches sémantiquement.

        ``item_id`` est toujours filtré (pas de self-match), en plus de
        ``exclude_ids``. Retour vide si l'item n'a pas d'embedding.
        """
        target = self._store.get(source_id, item_id)
        if target is None:
            return []
        if k <= 0:
            return []

        rows = [
            r
            for r in self._store.iter_source(source_id, model=model)
            if r.dim == target.dim
        ]
        if not rows:
            return []

        ids = [r.id for r in rows]
        matrix = np.vstack([r.vector for r in rows]).astype(np.float32, copy=False)

        excluded = frozenset({item_id}) | (exclude_ids or frozenset())
        pairs = top_k(
            target.vector,
            ids,
            matrix,
            k=k,
            exclude_ids=excluded,
            min_score=min_score,
        )
        return [Recommendation(item_id=i, score=s) for i, s in pairs]
