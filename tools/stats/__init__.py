"""tools.stats — Agrégation Python pour les stats publiques (ADR 0047).

Miroir du package TS `src/lib/stats/` côté pipeline. Expose :

- :func:`build_snapshot` : factory façade (pure fonction).
- :class:`StatsSnapshot` et dataclasses associées.

B-MED-12 — **Python 3.11+ requis** (``datetime.fromisoformat`` accepte
le suffixe ``Z`` à partir de 3.11). Tracé dans ``pyproject.toml``.
"""
from __future__ import annotations

from .aggregator import build_snapshot
from .models import (
    STATS_SCHEMA_VERSION,
    GlobalCounts,
    MonthlyBucket,
    StatsSnapshot,
    TopGuest,
    TopWork,
)
from .settings import StatsSettings

__all__ = [
    "STATS_SCHEMA_VERSION",
    "GlobalCounts",
    "MonthlyBucket",
    "StatsSettings",
    "StatsSnapshot",
    "TopGuest",
    "TopWork",
    "build_snapshot",
]
