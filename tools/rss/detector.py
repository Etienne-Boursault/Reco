"""rss.detector — diff `seen_guids` vs flux → nouveaux épisodes.

Règles :
- Un épisode est « nouveau » s'il a un GUID non vu dans `PollingState.seen_guids`.
- Premier run (état vierge) : tous les épisodes du flux sont a priori
  nouveaux mais on plafonne à `limit` pour éviter d'envoyer 200 notifs.
- L'ordre de retour est : plus récent d'abord (cf. ordre flux RSS).
"""
from __future__ import annotations

from .parser import ParsedEpisode, ParsedFeed
from .state import PollingState


def detect_new_episodes(
    feed: ParsedFeed,
    state: PollingState,
    *,
    limit: int | None = None,
) -> list[ParsedEpisode]:
    """Renvoie les épisodes du flux non présents dans `state.seen_guids`.

    `limit` (int>0) plafonne le nombre retourné — utile pour le premier
    run sur un podcast à 300+ épisodes (sinon on noierait Discord).
    `limit=None` ou `limit<=0` => pas de plafond.
    """
    seen = set(state.seen_guids)
    new_ones: list[ParsedEpisode] = []
    for ep in feed.episodes:
        if not ep.guid:
            continue
        if ep.guid in seen:
            continue
        new_ones.append(ep)
        if limit and limit > 0 and len(new_ones) >= limit:
            break
    return new_ones
