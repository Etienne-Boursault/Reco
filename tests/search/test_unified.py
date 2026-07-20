"""Tests search.unified — UnifiedSearchService + RRF fusion (ADR 0043)."""
from __future__ import annotations

import pytest

from cache.reader import SearchHit
from search.query import SearchQuery
from search.service import SearchResult
from search.similarity import SemanticHit
from search.unified import (
    RRF_K,
    UnifiedHit,
    UnifiedQuery,
    UnifiedSearchService,
    UnifiedStrategy,
    _fuse_ranks,
    _rrf_score,
)


# ---------- Mocks --------------------------------------------------------


class FakeLexical:
    """SearchService mock — retourne des résultats préconfigurés."""

    def __init__(
        self,
        items: tuple[SearchHit, ...] = (),
        episodes: tuple[SearchHit, ...] = (),
    ) -> None:
        self.items = items
        self.episodes = episodes
        self.calls: list[SearchQuery] = []

    def search(self, query: SearchQuery) -> SearchResult:
        self.calls.append(query)
        return SearchResult(items=self.items, episodes=self.episodes)


class FakeSemantic:
    """SemanticSearchService mock — retourne des hits préconfigurés."""

    def __init__(self, hits: tuple[SemanticHit, ...] = ()) -> None:
        self.hits = hits
        self.calls: list[tuple[str, str, int]] = []

    def similar_items(
        self, source_id: str, item_id: str, *, k: int = 10
    ) -> tuple[SemanticHit, ...]:
        self.calls.append((source_id, item_id, k))
        return self.hits


def _hit(item_id: str, source_id: str = "s", title: str = "t") -> SearchHit:
    return SearchHit(source_id=source_id, id=item_id, title=title, rank=0.0)


def _sem(item_id: str, source_id: str = "s", score: float = 0.9) -> SemanticHit:
    return SemanticHit(source_id=source_id, id=item_id, score=score)


# ---------- UnifiedQuery -------------------------------------------------


class TestUnifiedQuery:
    def test_defaults(self) -> None:
        q = UnifiedQuery(text="hi")
        assert q.strategy is UnifiedStrategy.LEXICAL_ONLY
        assert q.limit == 20
        assert q.anchor_item_id is None

    def test_text_must_be_str(self) -> None:
        with pytest.raises(TypeError):
            UnifiedQuery(text=42)  # type: ignore[arg-type]

    def test_strategy_must_be_enum(self) -> None:
        with pytest.raises(TypeError):
            UnifiedQuery(text="x", strategy="hybrid")  # type: ignore[arg-type]

    def test_limit_bounds(self) -> None:
        with pytest.raises(ValueError):
            UnifiedQuery(text="x", limit=0)
        with pytest.raises(ValueError):
            UnifiedQuery(text="x", limit=101)

    def test_frozen(self) -> None:
        q = UnifiedQuery(text="x")
        with pytest.raises(Exception):
            q.text = "y"  # type: ignore[misc]


# ---------- RRF arithmetic ----------------------------------------------


class TestRRF:
    def test_rrf_score_rank_1(self) -> None:
        assert _rrf_score(1) == pytest.approx(1.0 / (RRF_K + 1))

    def test_rrf_score_none_is_zero(self) -> None:
        assert _rrf_score(None) == 0.0

    def test_rrf_monotonic_decreasing(self) -> None:
        assert _rrf_score(1) > _rrf_score(2) > _rrf_score(10)

    def test_fuse_ranks_combines_doc_in_both(self) -> None:
        # 'a' apparaît rang 1 lex et rang 2 sem → score le plus haut.
        out = _fuse_ranks(["a", "b"], ["c", "a"])
        ids = [t[0] for t in out]
        assert ids[0] == "a"
        # Score 'a' = 1/(k+1) + 1/(k+2)
        assert out[0][3] == pytest.approx(
            1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 2)
        )
        assert out[0][1] == 1 and out[0][2] == 2

    def test_fuse_ranks_empty_lexical(self) -> None:
        out = _fuse_ranks([], ["x", "y"])
        ids = [t[0] for t in out]
        assert ids == ["x", "y"]
        assert all(t[1] is None for t in out)

    def test_fuse_ranks_empty_semantic(self) -> None:
        out = _fuse_ranks(["x", "y"], [])
        assert [t[0] for t in out] == ["x", "y"]
        assert all(t[2] is None for t in out)

    def test_fuse_ranks_tie_break_by_id(self) -> None:
        # Deux docs ex æquo (chacun rang 1 dans un seul backend) → id asc.
        out = _fuse_ranks(["b"], ["a"])
        assert [t[0] for t in out] == ["a", "b"]


# ---------- UnifiedSearchService ---------------------------------------


class TestLexicalOnly:
    def test_returns_items_then_episodes(self) -> None:
        lex = FakeLexical(
            items=(_hit("i1"), _hit("i2")),
            episodes=(_hit("e1"),),
        )
        svc = UnifiedSearchService(lex, semantic=None)
        result = svc.search(UnifiedQuery(text="q", source_id="s"))
        kinds = [h.kind for h in result]
        assert "item" in kinds and "episode" in kinds
        # ranks séquentiels
        assert result[0].lexical_rank == 1
        assert result[0].semantic_rank is None

    def test_empty_lexical(self) -> None:
        svc = UnifiedSearchService(FakeLexical(), semantic=None)
        result = svc.search(UnifiedQuery(text="rien", source_id="s"))
        assert result == ()

    def test_limit_truncates(self) -> None:
        lex = FakeLexical(items=tuple(_hit(f"i{i}") for i in range(50)))
        svc = UnifiedSearchService(lex, semantic=None)
        result = svc.search(UnifiedQuery(text="q", source_id="s", limit=5))
        assert len(result) == 5


class TestSemanticOnly:
    def test_uses_anchor(self) -> None:
        sem = FakeSemantic(hits=(_sem("a"), _sem("b")))
        svc = UnifiedSearchService(FakeLexical(), semantic=sem)
        result = svc.search(
            UnifiedQuery(
                text="",
                source_id="s",
                strategy=UnifiedStrategy.SEMANTIC_ONLY,
                anchor_item_id="anchor",
                limit=5,
            )
        )
        assert sem.calls == [("s", "anchor", 5)]
        assert [h.id for h in result] == ["a", "b"]
        assert result[0].lexical_rank is None
        assert result[0].semantic_rank == 1

    def test_falls_back_to_lexical_without_anchor(self) -> None:
        lex = FakeLexical(items=(_hit("x"),))
        sem = FakeSemantic()
        svc = UnifiedSearchService(lex, semantic=sem)
        result = svc.search(
            UnifiedQuery(
                text="q",
                source_id="s",
                strategy=UnifiedStrategy.SEMANTIC_ONLY,
                anchor_item_id=None,  # absent
            )
        )
        assert sem.calls == []
        assert [h.id for h in result] == ["x"]

    def test_falls_back_when_semantic_backend_none(self) -> None:
        lex = FakeLexical(items=(_hit("x"),))
        svc = UnifiedSearchService(lex, semantic=None)
        result = svc.search(
            UnifiedQuery(
                text="q",
                source_id="s",
                strategy=UnifiedStrategy.SEMANTIC_ONLY,
                anchor_item_id="a",
            )
        )
        assert [h.id for h in result] == ["x"]


class TestHybrid:
    def test_fuses_items_and_keeps_episodes_lexical(self) -> None:
        lex = FakeLexical(
            items=(_hit("a"), _hit("b"), _hit("c")),
            episodes=(_hit("ep1"),),
        )
        sem = FakeSemantic(hits=(_sem("c"), _sem("a"), _sem("d")))
        svc = UnifiedSearchService(lex, semantic=sem)
        result = svc.search(
            UnifiedQuery(
                text="q",
                source_id="s",
                strategy=UnifiedStrategy.HYBRID,
                anchor_item_id="anchor",
                limit=20,
            )
        )
        items_only = [h for h in result if h.kind == "item"]
        ids = [h.id for h in items_only]
        # 'a' et 'c' présents dans les deux backends → en tête.
        assert set(ids[:2]) == {"a", "c"}
        # 'd' seulement sémantique, 'b' seulement lexical → tous deux présents.
        assert "d" in ids and "b" in ids
        assert any(h.kind == "episode" for h in result)

    def test_hybrid_doc_in_both_outranks_doc_in_one(self) -> None:
        lex = FakeLexical(items=(_hit("solo"), _hit("both")))
        sem = FakeSemantic(hits=(_sem("both"),))
        svc = UnifiedSearchService(lex, semantic=sem)
        result = svc.search(
            UnifiedQuery(
                text="q",
                source_id="s",
                strategy=UnifiedStrategy.HYBRID,
                anchor_item_id="a",
            )
        )
        items = [h for h in result if h.kind == "item"]
        assert items[0].id == "both"
        assert items[0].lexical_rank == 2
        assert items[0].semantic_rank == 1
        assert items[0].combined_score > items[1].combined_score

    def test_hybrid_falls_back_when_no_anchor(self) -> None:
        lex = FakeLexical(items=(_hit("x"),))
        sem = FakeSemantic(hits=(_sem("y"),))
        svc = UnifiedSearchService(lex, semantic=sem)
        result = svc.search(
            UnifiedQuery(
                text="q",
                source_id="s",
                strategy=UnifiedStrategy.HYBRID,
                anchor_item_id=None,
            )
        )
        # Pas de fusion sémantique sans ancrage → résultats lexicaux purs.
        assert sem.calls == []
        assert [h.id for h in result] == ["x"]

    def test_hybrid_handles_empty_semantic(self) -> None:
        lex = FakeLexical(items=(_hit("x"), _hit("y")))
        sem = FakeSemantic(hits=())
        svc = UnifiedSearchService(lex, semantic=sem)
        result = svc.search(
            UnifiedQuery(
                text="q",
                source_id="s",
                strategy=UnifiedStrategy.HYBRID,
                anchor_item_id="a",
            )
        )
        ids = [h.id for h in result if h.kind == "item"]
        assert ids == ["x", "y"]

    def test_hybrid_handles_empty_lexical(self) -> None:
        lex = FakeLexical(items=(), episodes=())
        sem = FakeSemantic(hits=(_sem("a"), _sem("b")))
        svc = UnifiedSearchService(lex, semantic=sem)
        result = svc.search(
            UnifiedQuery(
                text="q",
                source_id="s",
                strategy=UnifiedStrategy.HYBRID,
                anchor_item_id="anchor",
            )
        )
        ids = [h.id for h in result if h.kind == "item"]
        assert ids == ["a", "b"]


class TestUnifiedHitShape:
    def test_unified_hit_is_frozen_dataclass(self) -> None:
        h = UnifiedHit(
            id="x",
            source_id="s",
            kind="item",
            lexical_rank=1,
            semantic_rank=None,
            combined_score=0.5,
        )
        with pytest.raises(Exception):
            h.id = "y"  # type: ignore[misc]
