"""tools.enrichment — refresh ciblé TMDB/Music avec flags `enrichedAt` par champ.

Cf. ADR 0023 + roadmap item #17.

Modules :
  - `duration`       : parse de durées humaines ("30d", "12w", "6m") → timedelta.
  - `tracker`        : EnrichedAtTracker — calcul "stale field" par item.
  - `field_refresher`: partial_update préservant les champs non touchés.
  - `http_cache`     : wrapper requests-cache (SQLite, TTL/endpoint).

Exceptions :
  - `EnrichedAtCorruptedError` : levée quand `item["enrichedAt"]` existe mais
    n'est pas un dict. P0-5 — on REFUSE d'écraser silencieusement un audit
    trail corrompu (risque perte d'historique non récupérable). Le caller
    doit catch et skip l'item.
"""
from __future__ import annotations

from .duration import parse_duration
from .field_refresher import EnrichedAtCorruptedError, partial_update
from .http_cache import build_cached_session
from .tracker import EnrichedAtTracker, stale_fields

__all__ = [
    "EnrichedAtCorruptedError",
    "EnrichedAtTracker",
    "build_cached_session",
    "parse_duration",
    "partial_update",
    "stale_fields",
]
