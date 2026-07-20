"""enrichment.settings — config injectable pour refresh_enrichment (P3.5-B).

Avant : ``refresh_enrichment.py`` hardcodait ses defaults dans
``argparse`` (older_than=90d, provider=all, pas de TTL par provider). Un
fork ne pouvait pas paramétrer la fraîcheur par source — viole l'ADR 0001
(SSOT) qui veut tout config par source dans ``SourceConfig.extra``.

Après : ``RefreshEnrichmentSettings`` factorise ces réglages et permet la
lecture depuis ``SourceConfig.extra["refresh_enrichment"]`` via le helper
``audit_core.settings.from_source_extra``. Les flags CLI restent
opérationnels (overrides).

Forward-compat :
  - ``ttl_per_provider`` : un fork peut définir des TTL différents par
    provider (ex. TMDB 90j, Music 180j). Le défaut est uniforme (basé sur
    ``older_than`` global).
  - ``prioritize_suspect`` : forward-compat pour pondérer les items
    auditer-flagged (cf. ADR 0019 sidecars d'audit) — pas encore consommé
    par ``run()`` mais réservé pour la prochaine itération.

Cf. ADR 0023 (re-enrich proactif).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from types import MappingProxyType
from typing import Any, Final, Literal

from audit_core.settings import from_source_extra as _from_source_extra

#: Seuil de fraîcheur par défaut : 90 jours (aligné CLI historique).
DEFAULT_OLDER_THAN: Final[timedelta] = timedelta(days=90)
#: Filtre provider par défaut : tous.
DEFAULT_PROVIDER_FILTER: Final[str] = "all"
#: TTL par provider (jours) — valeurs neutres = pas d'override (utilise
#: ``older_than`` global). Forward-compat ADR 0023.
DEFAULT_TTL_PER_PROVIDER: Final[Mapping[str, int]] = MappingProxyType({})

ProviderFilter = Literal["all", "tmdb", "music", "musicbrainz"]


def _coerce_older_than(v: Any) -> timedelta:
    """Accepte ``timedelta`` ou ``str`` ("30d", "12w" …) et coerce."""
    if isinstance(v, timedelta):
        return v
    if isinstance(v, str):
        # Import paresseux pour éviter cycle (duration → settings non utilisé).
        from enrichment.duration import parse_duration  # noqa: PLC0415

        return parse_duration(v)
    raise ValueError(f"older_than doit être timedelta ou str, reçu {type(v).__name__}")


@dataclass(frozen=True, slots=True)
class RefreshEnrichmentSettings:
    """Config injectable pour ``refresh_enrichment``.

    Attributs :
        older_than: seuil de fraîcheur global ; un champ est "stale" si
            ``now - enrichedAt[field] > older_than``. Défaut : 90 jours.
        provider_filter: ``"all"``, ``"tmdb"``, ``"music"`` (alias
            historique ``"musicbrainz"``).
        ttl_per_provider: TTL en jours par provider, override de
            ``older_than``. Mapping immuable (MappingProxyType).
            Forward-compat — pas encore consommé par ``run()`` mais
            réservé pour l'itération suivante (ADR 0023).
        prioritize_suspect: si vrai, priorise les items flaggés par
            ``enrich_audit`` (forward-compat).
    """

    older_than: timedelta = DEFAULT_OLDER_THAN
    provider_filter: str = DEFAULT_PROVIDER_FILTER
    ttl_per_provider: Mapping[str, int] = field(
        default_factory=lambda: DEFAULT_TTL_PER_PROVIDER,
    )
    prioritize_suspect: bool = False

    def __post_init__(self) -> None:
        # Coerce older_than depuis str si payload livre "30d".
        if not isinstance(self.older_than, timedelta):
            object.__setattr__(
                self, "older_than", _coerce_older_than(self.older_than),
            )
        if self.older_than.total_seconds() < 0:
            raise ValueError(
                f"older_than doit être positif (reçu {self.older_than})"
            )
        if self.provider_filter not in ("all", "tmdb", "music", "musicbrainz"):
            raise ValueError(
                f"provider_filter invalide : {self.provider_filter!r} "
                f"(attendu : all|tmdb|music|musicbrainz)"
            )
        if not isinstance(self.ttl_per_provider, Mapping):
            raise ValueError("ttl_per_provider doit être un Mapping")
        # Coerce vers MappingProxyType pour immutabilité réelle.
        if not isinstance(self.ttl_per_provider, MappingProxyType):
            object.__setattr__(
                self,
                "ttl_per_provider",
                MappingProxyType(dict(self.ttl_per_provider)),
            )
        for k, v in self.ttl_per_provider.items():
            if not isinstance(k, str):
                raise ValueError(
                    f"ttl_per_provider clé doit être str (reçu {type(k).__name__})"
                )
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(
                    f"ttl_per_provider[{k!r}] doit être int ≥ 0 (reçu {v!r})"
                )
        if not isinstance(self.prioritize_suspect, bool):
            raise ValueError("prioritize_suspect doit être un bool")

    @classmethod
    def from_source_extra(
        cls,
        extra: Mapping[str, Any] | None,
        *,
        overrides: Mapping[str, Any] | None = None,
    ) -> "RefreshEnrichmentSettings":
        """Construit depuis ``SourceConfig.extra["refresh_enrichment"]``.

        Délègue à ``audit_core.settings.from_source_extra`` (SSOT — ADR 0019).
        Les ``overrides`` (typiquement des flags CLI) gagnent sur la config.
        """
        return _from_source_extra(
            extra,
            "refresh_enrichment",
            cls,
            overrides=overrides,
        )


__all__ = [
    "DEFAULT_OLDER_THAN",
    "DEFAULT_PROVIDER_FILTER",
    "DEFAULT_TTL_PER_PROVIDER",
    "RefreshEnrichmentSettings",
]
