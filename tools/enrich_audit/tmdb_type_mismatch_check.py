"""Check #4 — Mismatch entre `Item.types` et la forme du payload TMDB.

C'est **le** check critique : il détecte le cas où le pipeline d'enrichis-
sement a matché un titre comme "movie" alors que l'œuvre originale est
une série (ou inversement). Avant ce check, on auditait l'intérieur des
checks (titre, année, durée) sans jamais valider que la *forme* du
payload TMDB correspondait au *type éditorial* de l'item.

Heuristique :
  - Item taggé FILM uniquement (pas de SERIES) + payload TMDB de type
    `tv` (champs `name`/`first_air_date`/`episode_run_time`) → CRITIQUE.
  - Item taggé SERIES uniquement (pas de FILM) + payload TMDB de type
    `movie` (champs `title`/`release_date`/`runtime`) → CRITIQUE.
  - Item taggé FILM **et** SERIES (cas multi-type rare) → on ne flag pas.
  - Item ni FILM ni SERIES (livre, musique, etc.) → no-op.

Détection du shape :
  - movie : présence de `release_date` OU `title`/`original_title` sans
    `first_air_date` ni `name`/`original_name`.
  - tv : présence de `first_air_date` OU `name`/`original_name` sans
    `release_date` ni `title`/`original_title`.
  - shape ambigu (champs des deux côtés) → on s'appuie sur
    `item.external_ids.tmdb_type` si disponible, sinon no-op (pas de
    faux positif).
"""
from __future__ import annotations

from domain.item import Item, ItemType

from .types import Severity, Suspicion, TmdbPayload

_MOVIE_KEYS = frozenset({"release_date", "title", "original_title", "runtime"})
_TV_KEYS = frozenset({"first_air_date", "name", "original_name", "episode_run_time"})


def _detect_tmdb_shape(tmdb_data: TmdbPayload) -> str | None:
    """Devine `"movie"` ou `"tv"` à partir de la forme du payload. ``None``
    si ambigu ou indéterminable."""
    keys = set(tmdb_data.keys())
    has_movie = bool(keys & _MOVIE_KEYS)
    has_tv = bool(keys & _TV_KEYS)
    if has_movie and not has_tv:
        return "movie"
    if has_tv and not has_movie:
        return "tv"
    return None


def check_tmdb_type_mismatch(
    item: Item,
    tmdb_data: TmdbPayload,
) -> Suspicion | None:
    """Renvoie une suspicion CRITICAL si le shape TMDB diverge du type Item."""
    types = set(item.types)
    is_film = ItemType.FILM in types
    is_series = ItemType.SERIES in types

    # Items multi-type FILM+SERIES (anthologies, format hybride) → on tolère.
    if is_film and is_series:
        return None
    # Items qui ne sont ni film ni série → check non applicable.
    if not (is_film or is_series):
        return None

    # 1) Détection par shape.
    shape = _detect_tmdb_shape(tmdb_data)
    # 2) Fallback : tmdb_type déclaré sur l'item.
    declared = item.external_ids.tmdb_type
    effective = shape or declared
    if effective is None:
        # Shape ambigu et pas de tmdb_type déclaré → on s'abstient.
        return None

    if is_film and effective == "tv":
        return Suspicion(
            kind="tmdb_type_mismatch",
            detail=(
                f"Item taggé film mais payload TMDB de type série "
                f"(shape={shape!r}, declared_tmdb_type={declared!r})"
            ),
            severity=Severity.CRITICAL,
        )
    if is_series and effective == "movie":
        return Suspicion(
            kind="tmdb_type_mismatch",
            detail=(
                f"Item taggé série mais payload TMDB de type film "
                f"(shape={shape!r}, declared_tmdb_type={declared!r})"
            ),
            severity=Severity.CRITICAL,
        )
    return None


# Métadonnées Check Protocol (CR archi P0 #1).
check_tmdb_type_mismatch.name = "tmdb_type_mismatch"  # type: ignore[attr-defined]
check_tmdb_type_mismatch.kind = "tmdb_type_mismatch"  # type: ignore[attr-defined]
check_tmdb_type_mismatch.description = (  # type: ignore[attr-defined]
    "Détecte un enrichissement TMDB dont la forme (movie vs tv) ne "
    "correspond pas au type éditorial de l'Item."
)


__all__ = ["check_tmdb_type_mismatch"]
