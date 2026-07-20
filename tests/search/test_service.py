"""Tests search.service — SearchService + SearchQuery."""
from __future__ import annotations

from pathlib import Path

import pytest

from cache.builder import CacheBuilder
from cache.reader import CacheReader
from search.query import SearchQuery, SearchScope
from search.service import SearchResult, SearchService


@pytest.fixture
def service(built_cache: tuple[Path, CacheBuilder]) -> SearchService:
    db_path, _ = built_cache
    reader = CacheReader(db_path)
    return SearchService(reader)


class TestSearchQuery:
    def test_defaults(self) -> None:
        q = SearchQuery(text="hi")
        assert q.scope is SearchScope.BOTH
        assert q.limit == 20
        assert q.source_id is None

    def test_text_must_be_str(self) -> None:
        with pytest.raises(TypeError):
            SearchQuery(text=123)  # type: ignore[arg-type]

    def test_limit_bounds(self) -> None:
        with pytest.raises(ValueError):
            SearchQuery(text="x", limit=0)
        with pytest.raises(ValueError):
            SearchQuery(text="x", limit=1000)

    def test_scope_type(self) -> None:
        with pytest.raises(TypeError):
            SearchQuery(text="x", scope="items")  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        q = SearchQuery(text="x")
        with pytest.raises((AttributeError, Exception)):
            q.text = "y"  # type: ignore[misc]


class TestSearchService:
    def test_search_both_scopes(self, service: SearchService) -> None:
        result = service.search(SearchQuery(text="Bong"))
        assert isinstance(result, SearchResult)
        assert any(h.id == "item-001" for h in result.items)
        assert any(h.id == "ep-A1" for h in result.episodes)

    def test_search_items_only(self, service: SearchService) -> None:
        result = service.search(
            SearchQuery(text="Bong", scope=SearchScope.ITEMS)
        )
        assert result.episodes == ()
        assert len(result.items) >= 1

    def test_search_episodes_only(self, service: SearchService) -> None:
        result = service.search(
            SearchQuery(text="Bong", scope=SearchScope.EPISODES)
        )
        assert result.items == ()
        assert len(result.episodes) >= 1

    def test_filter_by_source(self, service: SearchService) -> None:
        # "Invité B" n'existe qu'en source podcast-b.
        result = service.search(
            SearchQuery(text="Invité", source_id="podcast-b")
        )
        for h in result.items:
            assert h.source_id == "podcast-b"
        for h in result.episodes:
            assert h.source_id == "podcast-b"

    def test_filter_by_source_excludes_others(
        self, service: SearchService
    ) -> None:
        result = service.search(
            SearchQuery(text="Bong", source_id="podcast-b")
        )
        # Bong est uniquement en podcast-a → résultat doit être vide une fois
        # filtré.
        assert all(h.source_id == "podcast-b" for h in result.items)
        assert all(h.source_id == "podcast-b" for h in result.episodes)

    def test_limit_applied_after_filter(self, service: SearchService) -> None:
        result = service.search(
            SearchQuery(text="e", limit=2, scope=SearchScope.ITEMS)
        )
        assert len(result.items) <= 2

    def test_result_is_frozen_tuples(self, service: SearchService) -> None:
        result = service.search(SearchQuery(text="Bong"))
        assert isinstance(result.items, tuple)
        assert isinstance(result.episodes, tuple)
        with pytest.raises((AttributeError, Exception)):
            result.items = ()  # type: ignore[misc]
