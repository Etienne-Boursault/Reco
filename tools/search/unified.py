"""search.unified — Façade unifiée lexical (FTS5) + sémantique (cosine).

Cf. ADR 0043. Orchestre :class:`search.service.SearchService` (BM25) et
:class:`search.similarity.SemanticSearchService` (embeddings cosine) via
**Reciprocal Rank Fusion** (RRF) — voir Cormack et al., SIGIR 2009.

Module Python pur, stateless, sans dépendance autre que `search.*` et
`embeddings.*` déjà en place. Pensé pour être appelé depuis :

- CLI / scripts d'audit (Phase 3.5+).
- Endpoints build-time Astro (Phase 4+) — pas Phase 3.5.

La fusion s'applique au scope ``items`` uniquement (les embeddings P2.15
n'indexent pas les épisodes — cf. ADR 0033). Les épisodes restent
purement lexicaux.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from search.query import SearchQuery, SearchScope
from search.service import SearchService
from search.similarity import SemanticSearchService

# Constante RRF (Cormack 2009). Modifiable mais documenté côté ADR 0043.
RRF_K: Final[int] = 60

# Plafond strict — protège contre les requêtes pathologiques.
_MAX_LIMIT: Final[int] = 100
_DEFAULT_LIMIT: Final[int] = 20


class UnifiedStrategy(StrEnum):
    """Stratégie de fusion entre lexical et sémantique."""

    LEXICAL_ONLY = "lexical_only"
    SEMANTIC_ONLY = "semantic_only"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class UnifiedQuery:
    """Requête unifiée — frozen, validée au constructeur."""

    text: str
    source_id: str | None = None
    strategy: UnifiedStrategy = UnifiedStrategy.LEXICAL_ONLY
    limit: int = _DEFAULT_LIMIT
    # ID d'un item d'ancrage pour la branche sémantique. Si None et
    # strategy != LEXICAL_ONLY → la branche sémantique est désactivée
    # (on n'a pas d'embedding « depuis du texte libre » côté store P2.15).
    anchor_item_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text must be str")
        if not isinstance(self.strategy, UnifiedStrategy):
            raise TypeError("strategy must be UnifiedStrategy")
        if self.limit < 1 or self.limit > _MAX_LIMIT:
            raise ValueError(
                f"limit must be in [1, {_MAX_LIMIT}], got {self.limit}"
            )


@dataclass(frozen=True, slots=True)
class UnifiedHit:
    """Hit unifié : id, rangs natifs (None si absent), score RRF combiné."""

    id: str
    source_id: str | None
    kind: str  # "item" | "episode"
    lexical_rank: int | None
    semantic_rank: int | None
    combined_score: float


class _LexicalBackend(Protocol):
    """Sous-protocole consommé par la façade (DIP — facilite les mocks)."""

    def search(self, query: SearchQuery): ...  # noqa: D401


class _SemanticBackend(Protocol):
    """Sous-protocole consommé par la façade (DIP — facilite les mocks)."""

    def similar_items(
        self,
        source_id: str,
        item_id: str,
        *,
        k: int = ...,
    ): ...


def _rrf_score(rank: int | None, *, k: int = RRF_K) -> float:
    """RRF d'un document à un rang donné (1-indexé). ``None`` → 0.0."""
    if rank is None:
        return 0.0
    return 1.0 / (k + rank)


def _fuse_ranks(
    lexical_ids: list[str],
    semantic_ids: list[str],
    *,
    k: int = RRF_K,
) -> list[tuple[str, int | None, int | None, float]]:
    """Fusionne deux listes ordonnées par RRF.

    Retourne ``[(id, lex_rank, sem_rank, score), ...]`` trié par score
    décroissant, tie-break déterministe par ``id`` ascendant.
    """
    lex_rank: dict[str, int] = {doc_id: i + 1 for i, doc_id in enumerate(lexical_ids)}
    sem_rank: dict[str, int] = {doc_id: i + 1 for i, doc_id in enumerate(semantic_ids)}
    all_ids = set(lex_rank) | set(sem_rank)
    out: list[tuple[str, int | None, int | None, float]] = []
    for doc_id in all_ids:
        lr = lex_rank.get(doc_id)
        sr = sem_rank.get(doc_id)
        score = _rrf_score(lr, k=k) + _rrf_score(sr, k=k)
        out.append((doc_id, lr, sr, score))
    # Tri stable : score DESC, puis id ASC pour reproductibilité.
    out.sort(key=lambda t: (-t[3], t[0]))
    return out


class UnifiedSearchService:
    """Façade : oriente vers lexical, sémantique, ou fusion RRF.

    Le backend sémantique est **optionnel** : un déploiement sans
    ``embeddings.sqlite`` instancie la façade avec ``semantic=None`` ;
    ``HYBRID`` retombe alors sur ``LEXICAL_ONLY`` (graceful degradation,
    cf. ADR 0043).
    """

    def __init__(
        self,
        lexical: SearchService | _LexicalBackend,
        semantic: SemanticSearchService | _SemanticBackend | None = None,
    ) -> None:
        self._lexical = lexical
        self._semantic = semantic

    def search(self, query: UnifiedQuery) -> tuple[UnifiedHit, ...]:
        """Exécute la requête selon la stratégie demandée."""
        use_sem = (
            query.strategy is not UnifiedStrategy.LEXICAL_ONLY
            and self._semantic is not None
            and query.anchor_item_id is not None
            and query.source_id is not None
        )
        # Branch SEMANTIC_ONLY : on saute le moteur lexical entièrement.
        if query.strategy is UnifiedStrategy.SEMANTIC_ONLY and use_sem:
            return self._semantic_only(query)
        if query.strategy is UnifiedStrategy.SEMANTIC_ONLY and not use_sem:
            # Aucun ancrage sémantique exploitable → on retombe sur lexical.
            return self._lexical_only(query)

        if query.strategy is UnifiedStrategy.HYBRID and use_sem:
            return self._hybrid(query)

        return self._lexical_only(query)

    # ----- Implementations -----

    def _lexical_only(self, query: UnifiedQuery) -> tuple[UnifiedHit, ...]:
        result = self._lexical.search(
            SearchQuery(
                text=query.text,
                scope=SearchScope.BOTH,
                limit=query.limit,
                source_id=query.source_id,
            )
        )
        out: list[UnifiedHit] = []
        for rank, hit in enumerate(result.items, start=1):
            out.append(
                UnifiedHit(
                    id=hit.id,
                    source_id=getattr(hit, "source_id", query.source_id),
                    kind="item",
                    lexical_rank=rank,
                    semantic_rank=None,
                    combined_score=_rrf_score(rank),
                )
            )
        for rank, hit in enumerate(result.episodes, start=1):
            out.append(
                UnifiedHit(
                    id=hit.id,
                    source_id=getattr(hit, "source_id", query.source_id),
                    kind="episode",
                    lexical_rank=rank,
                    semantic_rank=None,
                    combined_score=_rrf_score(rank),
                )
            )
        return tuple(out[: query.limit])

    def _semantic_only(self, query: UnifiedQuery) -> tuple[UnifiedHit, ...]:
        assert self._semantic is not None and query.anchor_item_id is not None
        assert query.source_id is not None
        hits = self._semantic.similar_items(
            query.source_id, query.anchor_item_id, k=query.limit
        )
        return tuple(
            UnifiedHit(
                id=h.id,
                source_id=h.source_id,
                kind="item",
                lexical_rank=None,
                semantic_rank=rank,
                combined_score=_rrf_score(rank),
            )
            for rank, h in enumerate(hits, start=1)
        )

    def _hybrid(self, query: UnifiedQuery) -> tuple[UnifiedHit, ...]:
        assert self._semantic is not None and query.anchor_item_id is not None
        assert query.source_id is not None

        # Lexical (items + episodes) — fusion ne touche que items.
        lex_result = self._lexical.search(
            SearchQuery(
                text=query.text,
                scope=SearchScope.BOTH,
                limit=query.limit,
                source_id=query.source_id,
            )
        )
        lex_item_ids = [h.id for h in lex_result.items]
        sem_hits = self._semantic.similar_items(
            query.source_id, query.anchor_item_id, k=query.limit
        )
        sem_ids = [h.id for h in sem_hits]

        fused = _fuse_ranks(lex_item_ids, sem_ids)
        out: list[UnifiedHit] = [
            UnifiedHit(
                id=doc_id,
                source_id=query.source_id,
                kind="item",
                lexical_rank=lr,
                semantic_rank=sr,
                combined_score=score,
            )
            for doc_id, lr, sr, score in fused
        ]
        # Épisodes (lexical pur) ajoutés ensuite, classés par RRF lexical.
        for rank, hit in enumerate(lex_result.episodes, start=1):
            out.append(
                UnifiedHit(
                    id=hit.id,
                    source_id=getattr(hit, "source_id", query.source_id),
                    kind="episode",
                    lexical_rank=rank,
                    semantic_rank=None,
                    combined_score=_rrf_score(rank),
                )
            )
        # Tri global final + cap.
        out.sort(key=lambda h: (-h.combined_score, h.id))
        return tuple(out[: query.limit])


__all__ = [
    "RRF_K",
    "UnifiedHit",
    "UnifiedQuery",
    "UnifiedSearchService",
    "UnifiedStrategy",
]
