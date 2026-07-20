"""tools.meta.aggregator — Construit le `meta_index.json` à partir d'une
liste de registries déjà validés.

Fonctions PURES (testables sans réseau). Le fetcher/validator gèrent l'I/O.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

_RE_SLUG_FALLBACK = re.compile(r"[^a-z0-9.-]+")
_log = logging.getLogger(__name__)


def slug_from_site_url(site_url: str) -> str:
    """Réplique TS `slugFromSiteUrl` : host lowercase sans `www.`.

    Pour les inputs non-URL, fallback déterministe.
    M24-12 : on capture aussi `TypeError` (input non-string passé par mégarde).
    """
    if site_url is None:
        return "unknown"
    try:
        parsed = urlparse(site_url)
        if parsed.hostname:
            return parsed.hostname.lower().removeprefix("www.")
    except (ValueError, AttributeError, TypeError):
        pass
    try:
        s = str(site_url).lower()
    # B-LOW-1 — `BLE001` (catch-all `Exception`) volontaire : ce code est
    # un fallback de dernier recours appelé sur des inputs déjà non
    # standard ; on accepte qu'un `__str__` custom puisse lever
    # n'importe quoi et on renvoie un slug par défaut.
    except Exception:  # noqa: BLE001 — fallback ultime
        return "unknown"
    s = _RE_SLUG_FALLBACK.sub("-", s).strip("-")
    return s or "unknown"


def _sort_key_title(title: str) -> str:
    """L24-24 / B-LOW-3 — clé de tri stable inter-runtime.

    NFKD + casefold + suppression des marques combinantes, cohérent
    avec `_fr_sort_key` côté stats : "Étoile" et "Etoile" trient
    identiquement.
    """
    norm = unicodedata.normalize("NFKD", title)
    return "".join(c for c in norm if not unicodedata.combining(c)).casefold()


def dedupe_by_slug(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Élimine les doublons par `slug` — conserve la 1ʳᵉ entrée vue.

    B-MED-10 — log un `warning` quand un slug dupliqué est rencontré
    pour faciliter le diagnostic côté pipeline (deux registries qui
    publient le même `siteUrl`, ou une mauvaise résolution de slug).
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for e in entries:
        slug = e.get("slug")
        if not isinstance(slug, str):
            continue
        if slug in seen:
            _log.warning(
                "dedupe_by_slug: slug déjà vu, entrée ignorée (slug=%r, sourceUrl=%r)",
                slug,
                e.get("sourceUrl"),
            )
            continue
        seen.add(slug)
        out.append(e)
    return out


def aggregate_entries(
    entries_in: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construit le document `meta_index.json`.

    Args:
        entries_in: liste de `{sourceUrl, registry}` (registry DÉJÀ validé).
            B-NIT-3 — renommé depuis `items` (collision avec ``builtins.items``).

    Retour : dict prêt à être sérialisé.
    """
    entries: list[dict[str, Any]] = []
    for item in entries_in:
        registry = item["registry"]
        entries.append(
            {
                "sourceUrl": item["sourceUrl"],
                "slug": slug_from_site_url(registry["siteUrl"]),
                "registry": registry,
            }
        )
    entries = dedupe_by_slug(entries)

    # B-MED-11 — `.get(..., 0)` défensif sur les compteurs stats : un
    # registry minimaliste (forward-compat / fixture incomplète) ne doit
    # pas faire planter l'agrégation avec un KeyError.
    def _stat(e: dict[str, Any], key: str) -> int:
        return int(e["registry"].get("stats", {}).get(key, 0) or 0)

    # Tri : mentions desc, puis titre asc
    entries.sort(
        key=lambda e: (
            -_stat(e, "mentionsCount"),
            _sort_key_title(e["registry"]["podcast"]["title"]),
        )
    )

    totals = {
        "podcasts": len(entries),
        "items": sum(_stat(e, "itemsCount") for e in entries),
        "mentions": sum(_stat(e, "mentionsCount") for e in entries),
        "episodes": sum(_stat(e, "episodesCount") for e in entries),
        "guests": sum(_stat(e, "guestsCount") for e in entries),
    }
    return {
        "schemaVersion": 1,
        "entries": entries,
        "totals": totals,
    }
