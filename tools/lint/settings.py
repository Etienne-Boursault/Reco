"""Seuils + flags injectables du linter (CR archi #2, #5).

Pattern copié de ``tools/match_audit/settings.py`` : un seul dataclass
immuable qui agrège tous les seuils, construit soit depuis la CLI, soit
depuis ``SourceConfig.extra["lint"]``.

Permet :
  - de paramétrer les bornes year (H1, M6) côté source ;
  - d'injecter les seuils titre (H3) sans patcher le code ;
  - d'activer/désactiver des règles (CR archi #2) ;
  - d'injecter des patterns de titres suspects spécifiques à une source
    (CR archi #5 — source-awareness).

Toutes les valeurs ont un défaut raisonnable : un fork minimal n'a rien
à configurer pour démarrer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

from audit_core.settings import from_source_extra as _from_source_extra

# Defaults centralisés.
DEFAULT_YEAR_MIN: int = 1800
DEFAULT_YEAR_MAX: int = 2100
DEFAULT_TITLE_MIN_LEN: int = 3
DEFAULT_TITLE_MAX_LEN: int = 120
DEFAULT_TITLE_CAPS_THRESHOLD: int = 5
DEFAULT_TITLE_SUSPICIOUS_PATTERNS: tuple[str, ...] = (
    r"\(vost\)",
    r"\(saison\s+\d+\)",
    r"\(épisode\s+\d+\)",
    r"\(episode\s+\d+\)",
)


@dataclass(frozen=True, slots=True)
class LintSettings:
    """Settings injectables consommés par les règles.

    Toutes les bornes ont un défaut ; aucune règle n'a besoin de la
    configurer pour fonctionner. ``today`` est injecté pour le déterminisme
    des tests (M6/M9 — ``date.today()`` jamais appelé directement).
    """

    year_min: int = DEFAULT_YEAR_MIN
    year_max: int = DEFAULT_YEAR_MAX
    title_min_len: int = DEFAULT_TITLE_MIN_LEN
    title_max_len: int = DEFAULT_TITLE_MAX_LEN
    title_caps_threshold: int = DEFAULT_TITLE_CAPS_THRESHOLD
    title_suspicious_patterns: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_TITLE_SUSPICIOUS_PATTERNS,
    )
    enabled_rules: tuple[str, ...] | None = None
    """Si non-None, seules ces règles tournent. None = toutes."""
    disabled_rules: tuple[str, ...] = ()
    """Règles explicitement désactivées (gagne sur ``enabled_rules``)."""
    today: date = field(default_factory=date.today)
    """Date « aujourd'hui » injectable — utilisée par ``aberrant_values``
    pour le seuil « année future » (M6)."""

    def __post_init__(self) -> None:
        for name in ("year_min", "year_max", "title_min_len", "title_max_len",
                     "title_caps_threshold"):
            v = getattr(self, name)
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValueError(f"{name} doit être un int (reçu {type(v).__name__})")
        if self.year_min > self.year_max:
            raise ValueError(
                f"year_min ({self.year_min}) > year_max ({self.year_max})"
            )
        if self.title_min_len < 1:
            raise ValueError(f"title_min_len doit être ≥ 1 (reçu {self.title_min_len})")
        if self.title_max_len < self.title_min_len:
            raise ValueError("title_max_len < title_min_len")
        if not isinstance(self.title_suspicious_patterns, tuple):
            raise ValueError("title_suspicious_patterns doit être un tuple")
        if not all(isinstance(p, str) for p in self.title_suspicious_patterns):
            raise ValueError("title_suspicious_patterns ne contient que des str")
        if self.enabled_rules is not None and not isinstance(self.enabled_rules, tuple):
            raise ValueError("enabled_rules doit être un tuple ou None")
        if not isinstance(self.disabled_rules, tuple):
            raise ValueError("disabled_rules doit être un tuple")
        if not isinstance(self.today, date):
            raise ValueError("today doit être un date")

    @classmethod
    def from_source_extra(
        cls,
        extra: Mapping[str, Any] | None,
        *,
        overrides: Mapping[str, Any] | None = None,
    ) -> "LintSettings":
        """Construit depuis ``SourceConfig.extra["lint"]``.

        Délègue à ``audit_core.settings.from_source_extra`` (SSOT — ADR 0019).
        Les champs de type tuple sont coercés depuis list/tuple JSON.
        """
        return _from_source_extra(
            extra,
            "lint",
            cls,
            overrides=overrides,
            tuple_fields=frozenset({
                "title_suspicious_patterns",
                "enabled_rules",
                "disabled_rules",
            }),
        )

    def is_rule_enabled(self, name: str) -> bool:
        """True si ``name`` doit tourner d'après ``enabled_rules`` / ``disabled_rules``."""
        if name in self.disabled_rules:
            return False
        if self.enabled_rules is None:
            return True
        return name in self.enabled_rules


__all__ = [
    "DEFAULT_YEAR_MIN",
    "DEFAULT_YEAR_MAX",
    "DEFAULT_TITLE_MIN_LEN",
    "DEFAULT_TITLE_MAX_LEN",
    "DEFAULT_TITLE_CAPS_THRESHOLD",
    "DEFAULT_TITLE_SUSPICIOUS_PATTERNS",
    "LintSettings",
]
