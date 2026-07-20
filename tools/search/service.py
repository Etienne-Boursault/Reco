"""search.service — SearchService consommant un CacheReader.

Le filtre ``source_id`` est désormais poussé côté SQL (CR senior H8 /
CR archi P1-5) : plus de sur-fetch + post-filter Python — la requête
FTS5 inclut ``WHERE f.source_id = ?`` directement.

Le filtre ``field`` (CR archi P1-2) restreint la recherche à une colonne
FTS5 spécifique (``title`` / ``guests_text`` / ``hosts_text`` /
``recommended_by``) — utile pour la recherche multi-critère côté site.
"""
from __future__ import annotations

from dataclasses import dataclass

from cache.reader import CacheReader, SearchHit
from search.query import SearchField, SearchQuery, SearchScope


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Résultat final exposé aux consommateurs (Astro / CLI / tests)."""

    items: tuple[SearchHit, ...]
    episodes: tuple[SearchHit, ...]


class SearchService:
    """Service de recherche. Stateless ; sécuritaire en lecture concurrente."""

    def __init__(self, reader: CacheReader) -> None:
        self._reader = reader

    def search(self, query: SearchQuery) -> SearchResult:
        """Exécute une requête. Retourne items + episodes selon le scope."""
        items: tuple[SearchHit, ...] = ()
        episodes: tuple[SearchHit, ...] = ()

        items_column = self._items_column(query.field)
        episodes_column = self._episodes_column(query.field)

        if query.scope in (SearchScope.ITEMS, SearchScope.BOTH):
            if items_column is not None:  # field applicable à items
                items = tuple(
                    self._reader.search_items(
                        query.text,
                        limit=query.limit,
                        source_id=query.source_id,
                        column=items_column or None,
                    )
                )

        if query.scope in (SearchScope.EPISODES, SearchScope.BOTH):
            if episodes_column is not None:  # field applicable à episodes
                episodes = tuple(
                    self._reader.search_episodes(
                        query.text,
                        limit=query.limit,
                        source_id=query.source_id,
                        column=episodes_column or None,
                    )
                )

        return SearchResult(items=items, episodes=episodes)

    @staticmethod
    def _items_column(field: SearchField) -> str | None:
        """Mappe ``SearchField`` → colonne ``items_fts`` (ou ``None`` si
        pas applicable côté items).

        Retourne ``""`` pour ``ANY`` (pas de restriction colonne).
        """
        if field is SearchField.ANY:
            return ""
        if field in (SearchField.TITLE, SearchField.RECOMMENDED_BY, SearchField.GUEST):
            return field.value
        # HOST n'existe pas dans items_fts → on ne cherche pas côté items.
        return None

    @staticmethod
    def _episodes_column(field: SearchField) -> str | None:
        """Mappe ``SearchField`` → colonne ``episodes_fts``."""
        if field is SearchField.ANY:
            return ""
        if field in (SearchField.TITLE, SearchField.HOST, SearchField.GUEST):
            return field.value
        # RECOMMENDED_BY n'existe pas dans episodes_fts.
        return None
