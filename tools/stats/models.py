"""Dataclasses du snapshot `stats.json` (cf. ADR 0047).

Source de vérité côté Python — pendant strict de `src/lib/stats/types.ts`.
Tout changement doit être répercuté côté Zod (et bumper
`STATS_SCHEMA_VERSION` en cas de breaking change).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

STATS_SCHEMA_VERSION: int = 1


@dataclass(frozen=True)
class GlobalCounts:
    """Compteurs globaux (snapshot.global ou snapshot.perSource[*])."""

    podcastsCount: int = 0
    episodesCount: int = 0
    recommendationsCount: int = 0
    uniqueWorksCount: int = 0
    uniqueGuestsCount: int = 0

    def __post_init__(self) -> None:
        # B-LOW-9 — itérer directement sur les `dataclass_fields` évite
        # un `asdict()` (qui deep-copie récursivement) à chaque
        # instanciation. Ici tous les champs sont des `int` simples,
        # mais le pattern est correct par défaut.
        for f in fields(self):
            value = getattr(self, f.name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"GlobalCounts.{f.name} doit être un int ≥ 0 (reçu : {value!r})"
                )


@dataclass(frozen=True)
class TopGuest:
    name: str
    slug: str
    count: int


@dataclass(frozen=True)
class TopWork:
    id: str
    title: str
    type: str
    mentionsCount: int


@dataclass(frozen=True)
class MonthlyBucket:
    month: str  # `YYYY-MM`
    count: int


@dataclass
class StatsSnapshot:
    """Vue agrégée publique exposée par `stats.json`.

    Attribut ``global_`` (suffix ``_`` — B-NIT-7) : ``global`` est un
    mot réservé Python, le suffix est inéluctable côté dataclass.
    **Sérialisation : passer obligatoirement par :meth:`to_dict`** —
    `dataclasses.asdict()` direct produirait la clé ``global_`` qui
    casse la parité TS (clé attendue ``global``). Cf. L26-29.
    """

    generatedAt: str
    global_: GlobalCounts
    perSource: dict[str, GlobalCounts] = field(default_factory=dict)
    topGuests: list[TopGuest] = field(default_factory=list)
    topWorks: list[TopWork] = field(default_factory=list)
    typeDistribution: dict[str, int] = field(default_factory=dict)
    monthlyEpisodes: list[MonthlyBucket] = field(default_factory=list)
    schemaVersion: int = STATS_SCHEMA_VERSION

    def to_dict(self) -> dict:
        """Sérialisation au format strictement aligné avec le schéma TS."""
        return {
            "schemaVersion": self.schemaVersion,
            "generatedAt": self.generatedAt,
            "global": asdict(self.global_),
            "perSource": {k: asdict(v) for k, v in self.perSource.items()},
            "topGuests": [asdict(g) for g in self.topGuests],
            "topWorks": [asdict(w) for w in self.topWorks],
            "typeDistribution": dict(self.typeDistribution),
            "monthlyEpisodes": [asdict(b) for b in self.monthlyEpisodes],
        }
