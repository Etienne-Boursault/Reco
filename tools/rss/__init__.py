"""Package `rss` — poll de flux RSS et détection de nouveaux épisodes.

Sous-modules :
- `ports` : Protocols (FeedFetcher) pour DI / tests sans réseau.
- `parser` : wrapper feedparser → `ParsedFeed`/`ParsedEpisode` (dataclasses).
- `state` : PollingState JSON sidecar (atomic, schemaVersion, LRU bornée).
- `detector` : diff seenGuids vs feed → liste de nouveaux épisodes.

Le tout est testable sans réseau : injecter un `FeedFetcher` mock.
"""
from __future__ import annotations

from .detector import detect_new_episodes
from .parser import ParsedEpisode, ParsedFeed, parse_feed_bytes
from .ports import FeedFetcher
from .state import (
    MAX_SEEN_GUIDS,
    POLLING_STATE_SCHEMA_VERSION,
    PollingState,
    load_state,
    save_state,
)

__all__ = [
    "MAX_SEEN_GUIDS",
    "POLLING_STATE_SCHEMA_VERSION",
    "FeedFetcher",
    "ParsedEpisode",
    "ParsedFeed",
    "PollingState",
    "detect_new_episodes",
    "load_state",
    "parse_feed_bytes",
    "save_state",
]
