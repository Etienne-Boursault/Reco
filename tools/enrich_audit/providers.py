"""enrich_audit.providers — fabriques de `TmdbDataProvider`.

Séparé de :mod:`cli_runner` pour respecter SRP (CR archi P2 #6).

Format cache TMDB attendu (CR senior C4) :
  - **legacy** : payload TMDB brut à la racine (compat avec les fichiers
    existants dans ``tools/output/tmdb_cache/``).
  - **v1** : enveloppe versionnée
    ``{"_cacheVersion": 1, "kind": "movie"|"tv", "fetchedAt": ISO8601,
       "payload": {...payload TMDB brut...}}``.

Quand on rencontre un payload v1 dont le ``kind`` ne correspond pas au
``tmdb_type`` attendu, le provider renvoie ``None`` et compte un mismatch
(via le callable d'observation passé en option). Quand on rencontre un
payload legacy on l'accepte tel quel (rétro-compat).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Callable

from .service import TmdbDataProvider
from .types import TMDB_CACHE_VERSION

_log = logging.getLogger("reco.enrich_audit.providers")


def _coerce_cache_payload(raw: object) -> dict | None:
    """Renvoie le payload TMDB exploitable depuis le contenu d'un fichier
    cache, ou ``None`` si shape invalide.

    Accepte :
      - dict racine "legacy" → renvoyé tel quel.
      - dict v1 ``{"_cacheVersion": N, "payload": {...}}`` → renvoie
        ``payload`` si ``N`` correspond, sinon ``None``.
    """
    if not isinstance(raw, dict):
        return None
    version = raw.get("_cacheVersion")
    if version is None:
        # Legacy : payload brut à la racine.
        return raw
    if not isinstance(version, int) or version != TMDB_CACHE_VERSION:
        _log.warning(
            "Cache TMDB ignoré : _cacheVersion=%r attendu=%d",
            version, TMDB_CACHE_VERSION,
        )
        return None
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        _log.warning("Cache TMDB v1 sans payload exploitable")
        return None
    return payload


def make_cache_provider(
    cache_dir: Path,
    *,
    use_lru: bool = True,
    lru_maxsize: int = 1024,
) -> TmdbDataProvider:
    """Provider qui lit un cache local TMDB. Renvoie ``None`` si absent.

    Jamais d'appel réseau. Pour l'audit on s'appuie sur ce qui est sur
    disque ; si rien n'est cached, on skip (compté dans ``skipped_no_cache``).

    Args:
        cache_dir: dossier des fichiers ``<tmdb_id>.json``.
        use_lru: si ``True``, mémoïse via ``functools.lru_cache`` pour
            éviter de relire le même fichier N fois sur un gros dataset
            (CR senior H10).
        lru_maxsize: capacité du cache LRU.
    """
    def _read_raw(tmdb_id: int) -> dict | None:
        path = cache_dir / f"{tmdb_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return _coerce_cache_payload(data)

    if not use_lru:
        return _read_raw

    cached = lru_cache(maxsize=lru_maxsize)(_read_raw)

    def _wrapped(tmdb_id: int) -> dict | None:
        return cached(tmdb_id)

    # Expose pour permettre aux tests de purger.
    _wrapped.cache_clear = cached.cache_clear  # type: ignore[attr-defined]
    return _wrapped


__all__ = ["make_cache_provider"]
