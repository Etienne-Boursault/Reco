"""Check #3 — Cohérence runtime ↔ ItemType.

Heuristiques (seuils dans :mod:`.thresholds`) :
  - ItemType.FILM mais ``runtime`` TMDB < `DEFAULT_FILM_MIN_RUNTIME` →
    court-métrage probable. Reformulé "à vérifier" en INFO (CR senior H3).
  - ItemType.SERIES mais max(`episode_run_time`) >
    `DEFAULT_SERIES_EPISODE_MAX_RUNTIME` → TV-movie probable matché par
    erreur sur une série courte → WARNING (CR senior H2).
  - ItemType.SERIES mais max(`episode_run_time`) <
    `DEFAULT_SERIES_EPISODE_MIN_RUNTIME` → cartoon court / sketch matché
    comme série → INFO (CR senior H2).

Items sans type vidéo (livre, musique…) → no-op.
Runtime 0 / absent → no-op (pas de faux positif).
"""
from __future__ import annotations

from domain.item import Item, ItemType

from .thresholds import (
    DEFAULT_FILM_MIN_RUNTIME,
    DEFAULT_SERIES_EPISODE_MAX_RUNTIME,
    DEFAULT_SERIES_EPISODE_MIN_RUNTIME,
)
from .types import Severity, Suspicion, TmdbPayload


def _film_runtime(tmdb_data: TmdbPayload) -> int | None:
    val = tmdb_data.get("runtime")
    # bool est subclass int → exclure explicitement (CR senior L13)
    if not isinstance(val, int) or isinstance(val, bool) or val <= 0:
        return None
    return val


def _series_episode_runtime(tmdb_data: TmdbPayload) -> int | None:
    """Renvoie le runtime max de la liste ``episode_run_time`` (TMDB tv)."""
    val = tmdb_data.get("episode_run_time")
    if not isinstance(val, list) or not val:
        return None
    cleaned = [v for v in val if isinstance(v, int) and not isinstance(v, bool) and v > 0]
    if not cleaned:
        return None
    return max(cleaned)


def check_runtime_coherence(
    item: Item,
    tmdb_data: TmdbPayload,
    *,
    film_min_runtime: int = DEFAULT_FILM_MIN_RUNTIME,
    series_episode_max_runtime: int = DEFAULT_SERIES_EPISODE_MAX_RUNTIME,
    series_episode_min_runtime: int = DEFAULT_SERIES_EPISODE_MIN_RUNTIME,
) -> Suspicion | None:
    types = set(item.types)

    if ItemType.FILM in types:
        rt = _film_runtime(tmdb_data)
        if rt is not None and rt < film_min_runtime:
            return Suspicion(
                kind="runtime_short_film",
                detail=(
                    f"Item taggé film mais runtime TMDB = {rt} min "
                    f"(< {film_min_runtime} min) : court probable — vérifier"
                ),
                severity=Severity.INFO,
            )

    if ItemType.SERIES in types:
        rt = _series_episode_runtime(tmdb_data)
        if rt is not None:
            if rt > series_episode_max_runtime:
                return Suspicion(
                    kind="runtime_long_series",
                    detail=(
                        f"Item taggé série mais episode_run_time TMDB = {rt} min "
                        f"(> {series_episode_max_runtime} min) : TV-movie suspect"
                    ),
                    severity=Severity.WARNING,
                )
            if rt < series_episode_min_runtime:
                return Suspicion(
                    kind="runtime_short_series",
                    detail=(
                        f"Item taggé série mais episode_run_time TMDB = {rt} min "
                        f"(< {series_episode_min_runtime} min) : cartoon court / "
                        f"sketch suspect"
                    ),
                    severity=Severity.INFO,
                )

    return None


# Check Protocol metadata (CR archi P0 #1).
check_runtime_coherence.name = "runtime_coherence"  # type: ignore[attr-defined]
check_runtime_coherence.kind = "runtime_coherence"  # type: ignore[attr-defined]
check_runtime_coherence.description = (  # type: ignore[attr-defined]
    "Vérifie la cohérence du runtime TMDB avec le type éditorial (film vs "
    "série courte vs TV-movie)."
)


__all__ = ["check_runtime_coherence"]
