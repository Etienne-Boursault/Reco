"""enrich_audit.settings — seuils injectables (D-01/V-01, ADR 0019).

Avant : ``enrich_audit`` n'avait pas de ``settings`` symétrique aux deux
autres modules d'audit. Les seuils étaient passés en kwargs à
``default_service(title_threshold=..., year_tolerance=..., film_min_runtime=...)``,
non lus depuis ``SourceConfig.extra``.

Après : ``EnrichAuditSettings`` factorise les seuils et permet la
lecture depuis ``SourceConfig.extra["enrich_audit"]`` via le helper
``audit_core.settings.from_source_extra``.

Forward-compat : un fork peut désormais ajuster les seuils par source via
le fichier de config Astro plutôt que par flags CLI globaux.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from audit_core.settings import from_source_extra as _from_source_extra

from .thresholds import (
    DEFAULT_FILM_MIN_RUNTIME,
    DEFAULT_SERIES_EPISODE_MAX_RUNTIME,
    DEFAULT_SERIES_EPISODE_MIN_RUNTIME,
    DEFAULT_TITLE_THRESHOLD,
    DEFAULT_YEAR_TOLERANCE,
)

#: Runtime max film (pas de check officiel mais exposé pour symétrie).
DEFAULT_FILM_MAX_RUNTIME: int = 240


@dataclass(frozen=True, slots=True)
class EnrichAuditSettings:
    """Seuils injectables pour les checks ``enrich_audit``.

    Tous les seuils ont un défaut raisonnable (cf. ``thresholds.py``) ;
    aucun fork n'a besoin de les configurer pour démarrer.

    Attributs :
        title_threshold: similarité minimale titre Item ↔ TMDB.
        year_tolerance: tolérance ± années Item.year ↔ TMDB release.
        film_min_runtime: en dessous → court probable (suspicion).
        film_max_runtime: au-dessus → TV-movie probable (forward-compat).
        series_min_runtime: en dessous → cartoon/sketch matché par erreur.
        series_max_runtime: au-dessus → TV-movie probable.
    """

    title_threshold: float = DEFAULT_TITLE_THRESHOLD
    year_tolerance: int = DEFAULT_YEAR_TOLERANCE
    film_min_runtime: int = DEFAULT_FILM_MIN_RUNTIME
    film_max_runtime: int = DEFAULT_FILM_MAX_RUNTIME
    series_min_runtime: int = DEFAULT_SERIES_EPISODE_MIN_RUNTIME
    series_max_runtime: int = DEFAULT_SERIES_EPISODE_MAX_RUNTIME

    def __post_init__(self) -> None:
        if not isinstance(self.title_threshold, (int, float)) or isinstance(
            self.title_threshold, bool,
        ):
            raise ValueError("title_threshold doit être un nombre")
        if not 0.0 <= float(self.title_threshold) <= 1.0:
            raise ValueError(
                f"title_threshold hors borne [0,1]: {self.title_threshold}"
            )
        for name in (
            "year_tolerance",
            "film_min_runtime",
            "film_max_runtime",
            "series_min_runtime",
            "series_max_runtime",
        ):
            v = getattr(self, name)
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError(f"{name} doit être un int")
            if v < 0:
                raise ValueError(f"{name} doit être ≥ 0 (reçu {v})")
        if self.film_max_runtime < self.film_min_runtime:
            raise ValueError(
                f"film_max_runtime ({self.film_max_runtime}) < "
                f"film_min_runtime ({self.film_min_runtime})"
            )
        if self.series_max_runtime < self.series_min_runtime:
            raise ValueError(
                f"series_max_runtime ({self.series_max_runtime}) < "
                f"series_min_runtime ({self.series_min_runtime})"
            )

    @classmethod
    def from_source_extra(
        cls,
        extra: Mapping[str, Any] | None,
        *,
        overrides: Mapping[str, Any] | None = None,
    ) -> "EnrichAuditSettings":
        """Construit depuis ``SourceConfig.extra["enrich_audit"]``.

        Délègue à ``audit_core.settings.from_source_extra`` (SSOT — ADR 0019).
        """
        return _from_source_extra(
            extra,
            "enrich_audit",
            cls,
            overrides=overrides,
        )


__all__ = [
    "DEFAULT_FILM_MAX_RUNTIME",
    "EnrichAuditSettings",
]
