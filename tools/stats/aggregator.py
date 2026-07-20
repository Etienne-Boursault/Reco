"""Agrégation des stats publiques (pur Python, idempotent — ADR 0047).

Pendant du module TypeScript `src/lib/stats/aggregator.ts`. Mêmes invariants :

- exclusion des mentions `status='discarded'` ;
- exclusion des hôtes du podcast dans le décompte des invités uniques ;
- tri stable (locale FR pour les noms, ISO pour les mois) ;
- pas d'aléa, pas d'I/O — la lecture des collections est faite par
  `tools.build_stats`.

B-MED-12 — **Python 3.11+ requis** : on utilise ``datetime.fromisoformat``
qui n'accepte le suffixe ``Z`` natif qu'à partir de 3.11. Cette
dépendance est tracée dans ``pyproject.toml`` (``requires-python``).
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from .models import (
    GlobalCounts,
    MonthlyBucket,
    StatsSnapshot,
    TopGuest,
    TopWork,
)

_HIDDEN_STATUSES = frozenset({"discarded"})
_RE_NONALNUM = re.compile(r"[^a-z0-9]+")


# --- Helpers ----------------------------------------------------------------


def _slugify(value: str) -> str:
    """Slug ASCII minuscule cohérent avec `tools.common.slugify`."""
    if not value:
        return "x"
    norm = unicodedata.normalize("NFKD", value)
    norm = norm.encode("ascii", "ignore").decode("ascii").lower()
    norm = _RE_NONALNUM.sub("-", norm).strip("-")
    return norm or "x"


def _is_public(mention: Mapping[str, Any]) -> bool:
    return mention.get("status", "draft") not in _HIDDEN_STATUSES


def public_mentions(mentions: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Garde les mentions publiques (status != discarded)."""
    return [dict(m) for m in mentions if _is_public(m)]


def _build_hosts(sources: Iterable[Mapping[str, Any]]) -> set[str]:
    out: set[str] = set()
    for s in sources:
        for h in s.get("hosts") or []:
            k = str(h).strip().lower()
            if k:
                out.add(k)
    return out


def _month_key(value: Any) -> str | None:
    """Convertit une date (`datetime`, ISO string, None) en `YYYY-MM`."""
    if value is None or value == "":
        return None
    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            # `fromisoformat` accepte les ISO simples ; on retire un suffixe Z.
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def _fr_sort_key(s: str) -> str:
    """Clé de tri locale FR insensible aux accents/casses."""
    norm = unicodedata.normalize("NFKD", s)
    return "".join(c for c in norm if not unicodedata.combining(c)).lower()


# --- Computes ---------------------------------------------------------------


def compute_global_counts(
    *,
    sources: list[Mapping[str, Any]],
    episodes: list[Mapping[str, Any]],
    mentions: list[Mapping[str, Any]],
    items: list[Mapping[str, Any]],
) -> GlobalCounts:
    pub = public_mentions(mentions)
    hosts = _build_hosts(sources)
    mentioned_ids: set[str] = set()
    guests: set[str] = set()
    for m in pub:
        mentioned_ids.add(str(m["itemId"]))
        # B-MED-14 — guard `isinstance(..., str)` : un dataset legacy peut
        # avoir un `recommendedBy` typé int ou None. On veut un fail mou
        # (l'entrée est ignorée), pas un AttributeError sur `.strip()`.
        rec = m.get("recommendedBy")
        if not isinstance(rec, str):
            continue
        raw = rec.strip()
        if not raw:
            continue
        # B-MED-13 — `key = raw.lower()` : dédoublonnement insensible à la
        # casse (« Doe » et « doe » comptent comme un seul invité).
        # `.lower()` est suffisant ici (entrées libellées en latin) ;
        # le tri d'affichage utilise `_fr_sort_key` qui retire aussi les
        # accents pour le rang final.
        key = raw.lower()
        if key in hosts:
            continue
        guests.add(key)
    item_ids = {str(i["id"]) for i in items}
    unique_works = sum(1 for x in mentioned_ids if x in item_ids)
    return GlobalCounts(
        podcastsCount=len(sources),
        episodesCount=len(episodes),
        recommendationsCount=len(pub),
        uniqueWorksCount=unique_works,
        uniqueGuestsCount=len(guests),
    )


def compute_top_guests(
    mentions: list[Mapping[str, Any]],
    sources: list[Mapping[str, Any]],
    limit: int = 10,
) -> list[TopGuest]:
    hosts = _build_hosts(sources)
    counts: dict[str, dict[str, Any]] = {}
    for m in public_mentions(mentions):
        # B-MED-14 — même garde isinstance() que dans compute_global_counts.
        rec = m.get("recommendedBy")
        if not isinstance(rec, str):
            continue
        raw = rec.strip()
        if not raw:
            continue
        key = raw.lower()
        if key in hosts:
            continue
        entry = counts.setdefault(key, {"name": raw, "count": 0})
        entry["count"] += 1
    items = sorted(
        counts.values(),
        key=lambda e: (-e["count"], _fr_sort_key(e["name"])),
    )
    # M26-19 : dédoublonnement des slugs (parité TS `uniqueSlug`).
    used: set[str] = set()
    out: list[TopGuest] = []
    for e in items[:limit]:
        out.append(
            TopGuest(name=e["name"], slug=_unique_slug(e["name"], used), count=e["count"])
        )
    return out


def unique_slug(name: str, used: set[str]) -> str:
    """Pendant Python de `slug.ts::uniqueSlug` (M26-19).

    B-NIT-6 — exposé publiquement (sans préfixe `_`) car réutilisé par
    `compute_top_guests`. L'alias historique ``_unique_slug`` est
    conservé pour rétro-compat des imports existants.
    """
    return _unique_slug_impl(name, used)


def _unique_slug_impl(name: str, used: set[str]) -> str:
    root = _slugify(name)
    if root not in used:
        used.add(root)
        return root
    n = 2
    while f"{root}-{n}" in used:
        n += 1
    out = f"{root}-{n}"
    used.add(out)
    return out


#: Alias historique : conserve les imports existants `_unique_slug`.
_unique_slug = _unique_slug_impl


def compute_top_works(
    items: list[Mapping[str, Any]],
    mentions: list[Mapping[str, Any]],
    limit: int = 10,
) -> list[TopWork]:
    counts: dict[str, int] = {}
    for m in public_mentions(mentions):
        iid = str(m["itemId"])
        counts[iid] = counts.get(iid, 0) + 1
    by_id = {str(it["id"]): it for it in items}
    out: list[TopWork] = []
    for iid, n in counts.items():
        it = by_id.get(iid)
        if not it:
            continue
        types = it.get("types") or []
        primary = str(types[0]) if types else "autre"
        out.append(
            TopWork(
                id=iid,
                title=str(it["title"]),
                type=primary,
                mentionsCount=n,
            )
        )
    out.sort(key=lambda w: (-w.mentionsCount, _fr_sort_key(w.title)))
    return out[:limit]


def compute_type_distribution(
    items: list[Mapping[str, Any]],
    mentions: list[Mapping[str, Any]],
) -> dict[str, int]:
    mentioned = {str(m["itemId"]) for m in public_mentions(mentions)}
    dist: dict[str, int] = {}
    for it in items:
        if str(it["id"]) not in mentioned:
            continue
        types = it.get("types") or []
        key = str(types[0]) if types else "autre"
        dist[key] = dist.get(key, 0) + 1
    # L26-27 : tri secondaire count DESC puis alpha (parité TS).
    return dict(
        sorted(dist.items(), key=lambda kv: (-kv[1], _fr_sort_key(kv[0])))
    )


def compute_monthly_episodes(
    episodes: list[Mapping[str, Any]],
) -> list[MonthlyBucket]:
    """Agrège par mois ISO `YYYY-MM` et **remplit les mois manquants** entre
    min et max avec ``count=0`` (R-P3-30 — parité TS).
    """
    counts: dict[str, int] = {}
    for e in episodes:
        m = _month_key(e.get("date"))
        if not m:
            continue
        counts[m] = counts.get(m, 0) + 1
    if not counts:
        return []
    present = sorted(counts)
    first, last = present[0], present[-1]
    y, mo = int(first[:4]), int(first[5:7])
    y_last, mo_last = int(last[:4]), int(last[5:7])
    out: list[MonthlyBucket] = []
    while (y, mo) <= (y_last, mo_last):
        key = f"{y:04d}-{mo:02d}"
        out.append(MonthlyBucket(month=key, count=counts.get(key, 0)))
        mo += 1
        if mo > 12:
            mo = 1
            y += 1
    return out


def compute_per_source(
    *,
    sources: list[Mapping[str, Any]],
    episodes: list[Mapping[str, Any]],
    mentions: list[Mapping[str, Any]],
    items: list[Mapping[str, Any]],
) -> dict[str, GlobalCounts]:
    out: dict[str, GlobalCounts] = {}
    for s in sources:
        sid = str(s["id"])
        eps = [e for e in episodes if str(e.get("sourceId")) == sid]
        mens = [
            m
            for m in mentions
            if str(((m.get("sourceRef") or {}).get("sourceId")) or "") == sid
        ]
        ids = {str(m["itemId"]) for m in mens}
        its = [i for i in items if str(i["id"]) in ids]
        out[sid] = compute_global_counts(
            sources=[s], episodes=eps, mentions=mens, items=its
        )
    return out


# --- Façade -----------------------------------------------------------------


def build_snapshot(
    *,
    sources: list[Mapping[str, Any]],
    episodes: list[Mapping[str, Any]],
    mentions: list[Mapping[str, Any]],
    items: list[Mapping[str, Any]],
    source_id: str | None = None,
    top_guests_limit: int = 50,
    top_works_limit: int = 50,
    generated_at: str | None = None,
) -> StatsSnapshot:
    """Construit le snapshot agrégé (équivalent strict de `buildStatsSnapshot`).

    Si ``source_id`` est fourni, filtre toutes les collections sur cette source.
    """
    if source_id:
        sources = [s for s in sources if str(s.get("id")) == source_id]
        episodes = [
            e for e in episodes if str(e.get("sourceId")) == source_id
        ]
        mentions = [
            m
            for m in mentions
            if str((m.get("sourceRef") or {}).get("sourceId") or "") == source_id
        ]
        kept_ids = {str(m["itemId"]) for m in mentions}
        items = [i for i in items if str(i["id"]) in kept_ids]

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return StatsSnapshot(
        generatedAt=generated_at,
        global_=compute_global_counts(
            sources=sources, episodes=episodes, mentions=mentions, items=items
        ),
        perSource=compute_per_source(
            sources=sources, episodes=episodes, mentions=mentions, items=items
        ),
        topGuests=compute_top_guests(mentions, sources, top_guests_limit),
        topWorks=compute_top_works(items, mentions, top_works_limit),
        typeDistribution=compute_type_distribution(items, mentions),
        monthlyEpisodes=compute_monthly_episodes(episodes),
    )
