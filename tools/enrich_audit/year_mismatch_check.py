"""Check #2 — Écart d'année entre Item.year et TMDB release_date/first_air_date.

Tolérance ±1 par défaut (les sorties multi-pays décalent souvent l'année).
"""
from __future__ import annotations

import re

from domain.item import Item

from .thresholds import DEFAULT_YEAR_TOLERANCE
from .types import Severity, Suspicion, TmdbPayload

# CR senior L2 : rejette les chaînes du type "2010Z" ou "2010 bogus".
_RE_DATE = re.compile(r"^(\d{4})(?:-\d{2}-\d{2})?$")


def _pick_tmdb_year(tmdb_data: TmdbPayload) -> int | None:
    """Lit ``release_date`` (movie) ou ``first_air_date`` (tv) au format
    ``YYYY`` ou ``YYYY-MM-DD``. Renvoie ``None`` si absent ou malformé."""
    for key in ("release_date", "first_air_date"):
        val = tmdb_data.get(key)
        if not isinstance(val, str):
            continue
        match = _RE_DATE.match(val)
        if match is None:
            continue
        return int(match.group(1))
    return None


def check_year_mismatch(
    item: Item,
    tmdb_data: TmdbPayload,
    tolerance: int = DEFAULT_YEAR_TOLERANCE,
) -> Suspicion | None:
    """Renvoie une suspicion si ``|item.year - tmdb.year| > tolerance``.

    No-op si l'une des deux années est absente.
    """
    if item.year is None:
        return None
    tmdb_year = _pick_tmdb_year(tmdb_data)
    if tmdb_year is None:
        return None
    delta = abs(item.year - tmdb_year)
    if delta <= tolerance:
        return None
    # Gradation severity selon delta : un écart de 2 = WARNING, >10 = CRITICAL.
    severity = Severity.CRITICAL if delta > 10 else Severity.WARNING
    return Suspicion(
        kind="year_mismatch",
        detail=(
            f"Année item {item.year} ≠ TMDB {tmdb_year} "
            f"(écart {delta} > tolérance {tolerance})"
        ),
        severity=severity,
    )


# Check Protocol metadata (CR archi P0 #1).
check_year_mismatch.name = "year_mismatch"  # type: ignore[attr-defined]
check_year_mismatch.kind = "year_mismatch"  # type: ignore[attr-defined]
check_year_mismatch.description = (  # type: ignore[attr-defined]
    "Compare Item.year à la première date connue TMDB (release/first_air) "
    "avec une tolérance configurable."
)


__all__ = ["check_year_mismatch"]
