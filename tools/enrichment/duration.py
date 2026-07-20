"""Duration parser — convertit "30d", "12w", "6m", "2y", "48h" en timedelta.

Utilisé par `refresh_enrichment.py --refresh-older-than 90d`.

Format strict, insensible à la casse :
  - Nb entier >= 0
  - Suffixe d'unité : h(eures), d(ays), w(eeks), m(onths≈30j), y(ears≈365j)

Approximations : 1 mois = 30 jours, 1 année = 365 jours — suffisamment précis
pour des seuils de fraîcheur ("plus de 90 jours" ne demande pas la précision
calendaire).
"""
from __future__ import annotations

import re
from datetime import timedelta

_RE = re.compile(r"^\s*(\d+)\s*([hdwmy])\s*$", re.IGNORECASE)

_UNIT_DAYS = {
    "h": None,  # heures, traité séparément
    "d": 1,
    "w": 7,
    "m": 30,
    "y": 365,
}


def parse_duration(value: str) -> timedelta:
    """Parse "30d" / "12w" / "6m" / "2y" / "48h" → timedelta.

    Lève `ValueError` si le format est invalide ou si la valeur est négative.
    `0d` est autorisé (utile pour forcer le refresh complet en --dry-run).
    """
    if not isinstance(value, str):
        raise ValueError(f"duration must be a string, got {type(value).__name__}")
    m = _RE.match(value)
    if not m:
        raise ValueError(
            f"invalid duration {value!r} — expected '<int><h|d|w|m|y>' (e.g. '90d')"
        )
    n = int(m.group(1))
    unit = m.group(2).lower()
    if unit == "h":
        return timedelta(hours=n)
    return timedelta(days=n * _UNIT_DAYS[unit])
