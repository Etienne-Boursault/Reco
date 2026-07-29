"""Tests search.service — SearchService + SearchQuery."""
from __future__ import annotations

from pathlib import Path

import pytest

from cache.builder import CacheBuilder
from cache.reader import CacheReader
from search.query import SearchField, SearchQuery, SearchScope
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

    def test_field_defaults_to_any(self) -> None:
        assert SearchQuery(text="x").field is SearchField.ANY

    def test_field_type(self) -> None:
        with pytest.raises(TypeError):
            SearchQuery(text="x", field="title")  # type: ignore[arg-type]

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

    def test_field_any_searches_every_column(self, service: SearchService) -> None:
        """`ANY` = pas de restriction : « Bong » remonte l'item (via
        `recommended_by`) ET l'épisode (via son titre)."""
        result = service.search(SearchQuery(text="Bong", field=SearchField.ANY))
        assert any(h.id == "item-001" for h in result.items)
        assert any(h.id == "ep-A1" for h in result.episodes)

    def test_field_title_restricts_to_the_title_column(
        self, service: SearchService
    ) -> None:
        """« Bong » n'est PAS dans le titre de l'item (« Parasite ») : restreint
        à `title`, l'item disparaît alors qu'il sortait en `ANY`."""
        result = service.search(SearchQuery(text="Bong", field=SearchField.TITLE))
        assert result.items == ()
        assert any(h.id == "ep-A1" for h in result.episodes)

        by_title = service.search(
            SearchQuery(text="Parasite", field=SearchField.TITLE)
        )
        assert any(h.id == "item-001" for h in by_title.items)

    def test_field_recommended_by_has_no_episode_counterpart(
        self, service: SearchService
    ) -> None:
        """`recommended_by` n'existe pas dans `episodes_fts` → on ne cherche pas
        côté épisodes (au lieu de renvoyer du bruit)."""
        result = service.search(
            SearchQuery(text="Bong", field=SearchField.RECOMMENDED_BY)
        )
        assert any(h.id == "item-001" for h in result.items)
        assert result.episodes == ()

    def test_field_host_has_no_item_counterpart(
        self, service: SearchService
    ) -> None:
        """Symétrique : `hosts_text` n'existe pas dans `items_fts`."""
        result = service.search(SearchQuery(text="Kyan", field=SearchField.HOST))
        assert result.items == ()
        assert any(h.id == "ep-A1" for h in result.episodes)

    def test_field_guest_applies_to_both_tables(
        self, service: SearchService
    ) -> None:
        result = service.search(SearchQuery(text="Bong", field=SearchField.GUEST))
        assert any(h.id == "item-001" for h in result.items)
        assert any(h.id == "ep-A1" for h in result.episodes)

    def test_field_and_scope_combine(self, service: SearchService) -> None:
        """Scope EPISODES + field RECOMMENDED_BY : aucune table à interroger."""
        result = service.search(SearchQuery(
            text="Bong", scope=SearchScope.EPISODES,
            field=SearchField.RECOMMENDED_BY,
        ))
        assert result.items == ()
        assert result.episodes == ()

    def test_field_and_source_filter_combine(self, service: SearchService) -> None:
        result = service.search(SearchQuery(
            text="Invité", field=SearchField.GUEST, source_id="podcast-b",
        ))
        assert all(h.source_id == "podcast-b" for h in result.items)
        assert all(h.source_id == "podcast-b" for h in result.episodes)
        assert any(h.id == "ep-B1" for h in result.episodes)

    def test_column_mapping_is_exhaustive(self) -> None:
        """Garde-fou : toute valeur de `SearchField` doit être mappée
        explicitement (colonne ou `None`), jamais laissée au hasard."""
        expected_items = {
            SearchField.ANY: "",
            SearchField.TITLE: "title",
            SearchField.GUEST: "guests_text",
            SearchField.RECOMMENDED_BY: "recommended_by",
            SearchField.HOST: None,
        }
        expected_episodes = {
            SearchField.ANY: "",
            SearchField.TITLE: "title",
            SearchField.GUEST: "guests_text",
            SearchField.HOST: "hosts_text",
            SearchField.RECOMMENDED_BY: None,
        }
        for field in SearchField:
            assert SearchService._items_column(field) == expected_items[field]
            assert SearchService._episodes_column(field) == expected_episodes[field]

    def test_result_is_frozen_tuples(self, service: SearchService) -> None:
        result = service.search(SearchQuery(text="Bong"))
        assert isinstance(result.items, tuple)
        assert isinstance(result.episodes, tuple)
        with pytest.raises((AttributeError, Exception)):
            result.items = ()  # type: ignore[misc]
