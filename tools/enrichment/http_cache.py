"""HTTP cache SQLite — wrapper léger autour de `requests-cache`.

Cache des appels GET TMDB / MusicBrainz pour économiser quota API et accélérer
les passes successives de `refresh_enrichment`.

TTL par défaut (configurable) :
  - TMDB         : 24h  (les watch providers évoluent, les ids non).
  - MusicBrainz  : 7j   (données très stables).

Cache stocké dans `tools/output/http_cache.sqlite` (gitignored). Le wrapper
expose aussi un compteur hit/miss exploitable par le CLI pour métriques.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import requests_cache

# Endpoints regex → TTL (secondes). Premier match gagne.
DEFAULT_URL_TTL: list[tuple[str, int]] = [
    (r"api\.themoviedb\.org", 24 * 3600),
    (r"musicbrainz\.org", 7 * 24 * 3600),
    (r"api\.deezer\.com", 24 * 3600),
]


@dataclass
class CacheStats:
    """Compteur hit/miss accumulé sur la session courante."""

    hits: int = 0
    misses: int = 0
    requests: int = 0

    def hit_ratio(self) -> float:
        if self.requests == 0:
            return 0.0
        return self.hits / self.requests


@dataclass
class CachedSession:
    """Session HTTP cachée + stats. Wrap minimaliste pour usage CLI.

    Utilisable comme un `requests.Session` standard via `.get(...)`.
    """

    session: requests_cache.CachedSession
    stats: CacheStats = field(default_factory=CacheStats)

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        r = self.session.get(url, **kwargs)
        self.stats.requests += 1
        # `from_cache` est l'attribut posé par requests-cache.
        if getattr(r, "from_cache", False):
            self.stats.hits += 1
        else:
            self.stats.misses += 1
        return r

    def close(self) -> None:
        self.session.close()


def build_cached_session(
    cache_path: Path,
    *,
    default_ttl_seconds: int = 24 * 3600,
    url_ttls: Iterable[tuple[str, int]] | None = None,
    backend: str = "sqlite",
) -> CachedSession:
    """Construit une `CachedSession` prête à l'emploi.

    Args:
        cache_path: chemin du fichier SQLite. Le parent est créé au besoin.
        default_ttl_seconds: TTL par défaut si aucun pattern d'URL ne matche.
        url_ttls: liste de (regex_url, ttl_seconds). Défaut = DEFAULT_URL_TTL.
        backend: backend requests-cache ("sqlite" en prod, "memory" en tests).
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    rules = list(url_ttls) if url_ttls is not None else list(DEFAULT_URL_TTL)
    urls_expire_after: dict[str, int] = {pattern: ttl for pattern, ttl in rules}

    # `requests-cache` accepte un dict {pattern: expire_after} via
    # `urls_expire_after`. Le pattern utilise une regex compatible re.search.
    session = requests_cache.CachedSession(
        cache_name=str(cache_path.with_suffix("")) if backend == "sqlite" else "memory",
        backend=backend,
        expire_after=default_ttl_seconds,
        urls_expire_after=urls_expire_after,
        allowable_methods=("GET",),
        stale_if_error=True,
    )
    return CachedSession(session=session)
