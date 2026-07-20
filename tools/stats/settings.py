"""stats.settings — config injectable pour le pipeline `build_stats`.

Pattern Phase 3.5 / ADR 0033 — délègue à
``audit_core.settings.from_source_extra`` (SSOT). Permet à un fork de fixer
``topGuestsLimit`` / ``topWorksLimit`` / ``hidden_statuses`` par source via
``SourceConfig.extra["stats"]`` sans patcher le CLI.

Issues fixées : R-P1-25.

Forward-compat : payloads avec clés inconnues ignorés silencieusement.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from audit_core.settings import from_source_extra as _from_source_extra

#: Limite stockée dans le snapshot — R-P2-29 : le snapshot conserve jusqu'à
#: 50 entrées (forward-compat / fork qui voudrait afficher un Top 25), la
#: page UI tronque à 10 côté composant.
DEFAULT_TOP_GUESTS_LIMIT: Final[int] = 50
DEFAULT_TOP_WORKS_LIMIT: Final[int] = 50
#: Statuts à exclure des mentions « publiques » — SSOT côté Python.
DEFAULT_HIDDEN_STATUSES: Final[tuple[str, ...]] = ("discarded",)


@dataclass(frozen=True, slots=True)
class StatsSettings:
    """Config injectable pour ``build_stats``.

    Attributs :
        top_guests_limit: nb max d'invités exposés dans `topGuests`
            (le snapshot stocke jusqu'à `top_guests_limit` ; la page UI
            tronque à 10 par défaut — cf. R-P2-29).
        top_works_limit: idem pour `topWorks`.
        hidden_statuses: tuple des statuts de mention exclus du compte
            public. Doit contenir au moins ``"discarded"`` (invariant
            ADR 0047 — un fork peut ajouter ``"flagged"`` etc.).
    """

    top_guests_limit: int = DEFAULT_TOP_GUESTS_LIMIT
    top_works_limit: int = DEFAULT_TOP_WORKS_LIMIT
    hidden_statuses: tuple[str, ...] = field(default=DEFAULT_HIDDEN_STATUSES)

    def __post_init__(self) -> None:
        for name in ("top_guests_limit", "top_works_limit"):
            v = getattr(self, name)
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError(f"{name} doit être un int")
            if v <= 0:
                raise ValueError(f"{name} doit être > 0 (reçu {v})")
        if not isinstance(self.hidden_statuses, tuple):
            raise ValueError("hidden_statuses doit être un tuple[str, ...]")
        if not self.hidden_statuses:
            raise ValueError(
                "hidden_statuses doit contenir au moins 'discarded' "
                "(invariant ADR 0047)"
            )
        for s in self.hidden_statuses:
            if not isinstance(s, str) or not s:
                # B-LOW-10 — pas de `repr(s)` : on évite de logguer un
                # payload arbitraire (PII / secret embarqué accidentel)
                # dans une exception remontée potentiellement en clair.
                raise ValueError(
                    "hidden_statuses[*] doit être une str non vide "
                    f"(type reçu : {type(s).__name__})"
                )

    @classmethod
    def from_source_extra(
        cls,
        extra: Mapping[str, Any] | None,
        *,
        overrides: Mapping[str, Any] | None = None,
    ) -> "StatsSettings":
        """Construit depuis ``SourceConfig.extra["stats"]``."""
        return _from_source_extra(
            extra,
            "stats",
            cls,
            overrides=overrides,
            tuple_fields=frozenset({"hidden_statuses"}),
        )


__all__ = [
    "DEFAULT_HIDDEN_STATUSES",
    "DEFAULT_TOP_GUESTS_LIMIT",
    "DEFAULT_TOP_WORKS_LIMIT",
    "StatsSettings",
]
