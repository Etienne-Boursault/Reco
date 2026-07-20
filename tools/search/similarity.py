"""search.similarity — API publique : recherche par similarité sémantique.

Pont mince entre :class:`search` (FTS5 lexical) et :mod:`embeddings`
(cosine vectoriel). Le but n'est PAS de fusionner les deux moteurs ici
(hybrid search reporté à un futur item) mais d'exposer une API
homogène pour les consommateurs : ``SemanticSearchService`` retourne
des :class:`SemanticHit` analogues aux ``SearchHit`` FTS5.

Ne casse PAS l'API ``search.SearchService`` (P2.8) : c'est un *ajout*.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from embeddings.dedup import CrossEpisodeDedup, DedupPair
from embeddings.ports import EmbeddingStorePort
from embeddings.recommend import Recommendation, SimilarityRecommender

# Re-exports pour les consommateurs (un seul import depuis search).
__all__ = [
    "DEFAULT_TOP_K",
    "DEFAULT_DEDUP_THRESHOLD",
    "DedupPair",
    "Recommendation",
    "SemanticHit",
    "SemanticSearchService",
]

DEFAULT_TOP_K: Final[int] = 10
DEFAULT_DEDUP_THRESHOLD: Final[float] = 0.85


@dataclass(frozen=True, slots=True)
class SemanticHit:
    """Résultat d'une recherche sémantique : item + score cosinus."""

    source_id: str
    id: str
    score: float


class SemanticSearchService:
    """Façade homogène autour de :class:`SimilarityRecommender` et
    :class:`CrossEpisodeDedup`.

    Stateless ; tout vit dans le ``store`` injecté.
    """

    def __init__(self, store: EmbeddingStorePort) -> None:
        self._store = store
        self._recommender = SimilarityRecommender(store)
        self._dedup = CrossEpisodeDedup(store)

    def similar_items(
        self,
        source_id: str,
        item_id: str,
        *,
        k: int = DEFAULT_TOP_K,
        model: str | None = None,
        exclude_ids: frozenset[str] | None = None,
        min_score: float = -1.0,
    ) -> tuple[SemanticHit, ...]:
        """Items les plus proches sémantiquement de ``(source_id, item_id)``."""
        recos = self._recommender.top_k(
            source_id,
            item_id,
            k=k,
            model=model,
            exclude_ids=exclude_ids,
            min_score=min_score,
        )
        return tuple(
            SemanticHit(source_id=source_id, id=r.item_id, score=r.score)
            for r in recos
        )

    def dedup_pairs(
        self,
        source_id: str,
        *,
        threshold: float = DEFAULT_DEDUP_THRESHOLD,
        model: str | None = None,
        max_pairs: int | None = None,
    ) -> tuple[DedupPair, ...]:
        """Paires d'items potentiellement doublons (score ≥ threshold)."""
        return tuple(
            self._dedup.suggest(
                source_id,
                threshold=threshold,
                model=model,
                max_pairs=max_pairs,
            )
        )
