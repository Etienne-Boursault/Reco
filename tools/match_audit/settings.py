"""Seuils + flags injectables (CR senior H1/M3, CR archi #5).

Une seule structure ``MatchAuditSettings`` qui agrège tous les seuils,
construite soit depuis la CLI, soit depuis ``SourceConfig.extra["match_audit"]``
(forward-compat — l'extension officielle de ``SourceConfig`` est
documentée dans ADR 0015, mais on lit déjà l'``extra`` pour ne pas
bloquer l'agent P1.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from audit_core.settings import from_source_extra as _from_source_extra

# Defaults centralisés — un seul endroit où les ajuster.
DEFAULT_DURATION_TOLERANCE: float = 0.05
DEFAULT_INTRO_THRESHOLD: float = 0.4
DEFAULT_INTRO_CHARS: int = 500
DEFAULT_TITLE_THRESHOLD: float = 0.3


@dataclass(frozen=True, slots=True)
class MatchAuditSettings:
    duration_tolerance: float = DEFAULT_DURATION_TOLERANCE
    intro_threshold: float = DEFAULT_INTRO_THRESHOLD
    intro_chars: int = DEFAULT_INTRO_CHARS
    title_threshold: float = DEFAULT_TITLE_THRESHOLD
    # Si un fork ne veut PAS d'un check, on désactive ici. ``None`` = tous activés.
    enabled_checks: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        for name in ("duration_tolerance", "intro_threshold", "title_threshold"):
            v = getattr(self, name)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise ValueError(f"{name} doit être un nombre, pas {type(v).__name__}")
            if not 0.0 <= float(v) <= 1.0:
                raise ValueError(f"{name} hors borne [0,1]: {v}")
        if not isinstance(self.intro_chars, int) or isinstance(self.intro_chars, bool):
            raise ValueError("intro_chars doit être un int")
        if self.intro_chars <= 0:
            raise ValueError(f"intro_chars doit être > 0 (reçu {self.intro_chars})")
        if self.enabled_checks is not None and not isinstance(
            self.enabled_checks, tuple,
        ):
            raise ValueError("enabled_checks doit être un tuple ou None")

    @classmethod
    def from_source_extra(
        cls,
        extra: Mapping[str, Any] | None,
        *,
        overrides: Mapping[str, Any] | None = None,
    ) -> "MatchAuditSettings":
        """Construit un settings depuis ``SourceConfig.extra["match_audit"]``.

        Délègue à ``audit_core.settings.from_source_extra`` (SSOT — ADR 0019).
        """
        return _from_source_extra(
            extra,
            "match_audit",
            cls,
            overrides=overrides,
            tuple_fields=frozenset({"enabled_checks"}),
        )


__all__ = [
    "DEFAULT_DURATION_TOLERANCE",
    "DEFAULT_INTRO_CHARS",
    "DEFAULT_INTRO_THRESHOLD",
    "DEFAULT_TITLE_THRESHOLD",
    "MatchAuditSettings",
]
