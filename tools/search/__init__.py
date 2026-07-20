"""tools.search — Service de recherche full-text au-dessus du cache SQLite.

Couche haute consommant un `CacheReader` (DIP). Fournit une API simple
type `SearchService.search(query)` orientée site public Astro.
"""
from __future__ import annotations

from search.query import SearchField, SearchQuery, SearchScope
from search.service import SearchResult, SearchService

__all__ = [
    "SearchField",
    "SearchQuery",
    "SearchResult",
    "SearchScope",
    "SearchService",
]
