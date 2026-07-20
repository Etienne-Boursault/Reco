"""search.query — DTO d'entrée du SearchService.

Immutable, frozen + slots. Validation au constructeur (input boundary).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

# Limites raisonnables : protège contre les requêtes pathologiques.
_MAX_LIMIT: Final[int] = 100
_DEFAULT_LIMIT: Final[int] = 20


class SearchScope(StrEnum):
    """Sur quelles tables FTS5 chercher."""

    ITEMS = "items"
    EPISODES = "episodes"
    BOTH = "both"


class SearchField(StrEnum):
    """Filtre par colonne FTS5 (CR archi P1-2 / ADR 0027).

    Mappe vers les colonnes FTS5 ``items_fts`` / ``episodes_fts``.
    ``ANY`` = recherche dans toutes les colonnes (défaut FTS5).
    """

    ANY = "any"
    TITLE = "title"
    GUEST = "guests_text"
    HOST = "hosts_text"
    RECOMMENDED_BY = "recommended_by"


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Requête de recherche — frozen, validée au constructeur."""

    text: str
    scope: SearchScope = SearchScope.BOTH
    limit: int = _DEFAULT_LIMIT
    source_id: str | None = None
    field: SearchField = SearchField.ANY

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text must be str")
        if self.limit < 1 or self.limit > _MAX_LIMIT:
            raise ValueError(
                f"limit must be in [1, {_MAX_LIMIT}], got {self.limit}"
            )
        if not isinstance(self.scope, SearchScope):
            raise TypeError("scope must be SearchScope")
        if not isinstance(self.field, SearchField):
            raise TypeError("field must be SearchField")
