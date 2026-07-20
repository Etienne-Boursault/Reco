"""rss.parser — wrapper feedparser → dataclasses normalisées.

On évite d'exposer les types feedparser bruts (FeedParserDict) car ils
sont historiquement instables (clés manquantes, encodage ambigu). Tous
les consommateurs reçoivent des `ParsedFeed`/`ParsedEpisode` immutables.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedEpisode:
    """Un épisode parsé d'un flux RSS.

    `guid` est l'identifiant stable — pris dans `entry.id` ou, en repli,
    `entry.guid` ou `entry.link`. C'est la clé utilisée pour la dédup.
    """

    guid: str
    title: str
    link: str
    published: str  # ISO-8601 si parseable, sinon string brute du flux.
    summary: str = ""


@dataclass(frozen=True, slots=True)
class ParsedFeed:
    """Un flux RSS parsé : métadonnées + liste d'épisodes triés du + récent au + ancien."""

    title: str
    feed_url: str
    episodes: tuple[ParsedEpisode, ...]


def _pick_guid(entry: object) -> str:
    """Récupère un identifiant stable depuis une entry feedparser.

    Ordre : `id` → `guid` → `link` → string vide. La string vide est
    filtrée plus haut (épisode ignoré) car sans GUID on ne peut pas
    déduper proprement.
    """
    for key in ("id", "guid", "link"):
        value = getattr(entry, key, None)
        if value is None and isinstance(entry, dict):
            value = entry.get(key)
        if value:
            return str(value)
    return ""


def _pick_published(entry: object) -> str:
    """Renvoie l'instant de publication en ISO-8601 si possible, sinon string brute.

    feedparser remplit `published_parsed` (time.struct_time) quand il a su
    parser la date. On préfère l'ISO-8601 reconstitué pour homogénéité.
    """
    from datetime import datetime, timezone  # noqa: PLC0415 — import paresseux

    parsed = getattr(entry, "published_parsed", None)
    if parsed is None and isinstance(entry, dict):
        parsed = entry.get("published_parsed")
    if parsed is not None:
        try:
            dt = datetime(*parsed[:6], tzinfo=timezone.utc)
            return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError):
            pass
    raw = getattr(entry, "published", None)
    if raw is None and isinstance(entry, dict):
        raw = entry.get("published")
    return str(raw) if raw else ""


def parse_feed_bytes(body: bytes, *, fallback_url: str = "") -> ParsedFeed:
    """Parse les octets d'un flux RSS et renvoie un `ParsedFeed`.

    `fallback_url` est utilisé si le flux ne déclare pas son URL self.
    Les épisodes sans GUID utilisable sont filtrés.
    """
    import feedparser  # noqa: PLC0415 — import paresseux pour tests purs.

    fp = feedparser.parse(body)
    feed_meta = getattr(fp, "feed", {}) or {}
    title = str(feed_meta.get("title", "") if isinstance(feed_meta, dict)
                else getattr(feed_meta, "title", "")) or ""
    # `link` (page web) ou `id` (auto-référence) ; on n'a pas besoin de
    # garantir la qualité — sert juste à logger / metadata.
    feed_url = fallback_url
    episodes: list[ParsedEpisode] = []
    for entry in getattr(fp, "entries", []) or []:
        guid = _pick_guid(entry)
        if not guid:
            continue
        title_e = getattr(entry, "title", None)
        if title_e is None and isinstance(entry, dict):
            title_e = entry.get("title", "")
        link = getattr(entry, "link", None)
        if link is None and isinstance(entry, dict):
            link = entry.get("link", "")
        summary = getattr(entry, "summary", None)
        if summary is None and isinstance(entry, dict):
            summary = entry.get("summary", "")
        episodes.append(
            ParsedEpisode(
                guid=guid,
                title=str(title_e or ""),
                link=str(link or ""),
                published=_pick_published(entry),
                summary=str(summary or ""),
            ),
        )
    return ParsedFeed(title=title, feed_url=feed_url, episodes=tuple(episodes))
