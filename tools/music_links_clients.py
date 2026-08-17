"""Clients HTTP Deezer et iTunes — couche RÉSEAU.

Isolée pour être substituable en test : c'est la seule couche qui sort de la
machine, et la seule dont l'échec ne signifie pas « pas de correspondance »
mais « on n'a pas pu savoir ». La distinction compte, un 429 déguisé en
`no-match` faisant passer un problème d'infrastructure pour un refus de fond.

Extraite de `enrich_music_links.py` (cf. `music_links_matching`).
"""
from __future__ import annotations

import time
from typing import Any

import requests

from common import log
from music_links_matching import (
    DEEZER_BASE,
    HTTP_TIMEOUT,
    HTTP_TOO_MANY_REQUESTS,
    ITUNES_BASE,
    PLATFORM_APPLE,
    PLATFORM_DEEZER,
    RETRY_AFTER_SLEEP,
    SEARCH_LIMIT,
    Candidate,
)


def get_json(session: requests.Session, url: str,
             params: dict[str, Any] | None = None,
             *, retries: int = 1) -> dict[str, Any] | None:
    """GET → dict JSON, ou None en cas d'erreur réseau/HTTP/parse.

    Un HTTP 429 est réessayé après une pause (cf. `RETRY_AFTER_SLEEP`) : le
    confondre avec une absence de résultat fausserait le rapport.
    """
    try:
        resp = session.get(url, params=params, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        log.error("  HTTP %s : %s", url, exc)
        return None
    if resp.status_code == HTTP_TOO_MANY_REQUESTS and retries > 0:
        log.warning("  %s → HTTP 429, pause de %.0fs puis réessai",
                    url, RETRY_AFTER_SLEEP)
        time.sleep(RETRY_AFTER_SLEEP)
        return get_json(session, url, params, retries=retries - 1)
    if resp.status_code != 200:
        log.error("  %s → HTTP %s", url, resp.status_code)
        return None
    try:
        data = resp.json()
    except ValueError:
        log.error("  %s → réponse non-JSON", url)
        return None
    return data if isinstance(data, dict) else None


def deezer_search(session: requests.Session, kind: str,
                  query: str) -> list[dict[str, Any]]:
    """Recherche Deezer. Liste vide en cas d'erreur ou de réponse vide."""
    data = get_json(session, f"{DEEZER_BASE}/search/{kind}",
                    {"q": query, "limit": SEARCH_LIMIT})
    if not data or data.get("error"):
        return []
    results = data.get("data")
    return results if isinstance(results, list) else []


def deezer_by_id(session: requests.Session, kind: str,
                 deezer_id: str) -> dict[str, Any] | None:
    """Fiche Deezer par identifiant.

    Deezer répond HTTP 200 avec `{"error": …}` pour un id inexistant — d'où le
    contrôle explicite.
    """
    data = get_json(session, f"{DEEZER_BASE}/{kind}/{deezer_id}")
    if not data or data.get("error"):
        return None
    return data


def itunes_search(session: requests.Session, entity: str,
                  term: str) -> list[dict[str, Any]]:
    """Recherche iTunes/Apple Music. Liste vide en cas d'erreur."""
    data = get_json(session, f"{ITUNES_BASE}/search",
                    {"term": term, "entity": entity, "country": "FR",
                     "limit": SEARCH_LIMIT})
    if not data:
        return []
    results = data.get("results")
    return results if isinstance(results, list) else []


# ===========================================================================
# Normalisation des payloads en `Candidate`
# ===========================================================================
def deezer_candidate(payload: dict[str, Any], kind: str) -> Candidate | None:
    """Convertit un résultat Deezer en `Candidate`. None si inexploitable.

    Un résultat sans `link` ne mène nulle part : impossible d'en tirer une URL
    sans la fabriquer, ce que la doctrine interdit.
    """
    url = payload.get("link")
    if not url:
        return None
    artist = (payload.get("artist") or {}).get("name") or ""
    if kind == "artist":
        artist = payload.get("name") or artist
        title = ""
    else:
        title = payload.get("title") or ""
    return Candidate(PLATFORM_DEEZER, kind, str(url), str(artist), str(title),
                     ident=str(payload.get("id") or ""))


#: Champ iTunes portant l'URL publique, selon l'entité recherchée.
_ITUNES_URL_FIELD = {"song": "trackViewUrl", "album": "collectionViewUrl",
                     "musicArtist": "artistViewUrl"}
#: Entité iTunes correspondant à chaque type de contenu Deezer.
ITUNES_ENTITY = {"track": "song", "album": "album", "artist": "musicArtist"}


def itunes_candidate(payload: dict[str, Any], kind: str) -> Candidate | None:
    """Convertit un résultat iTunes en `Candidate`. None si inexploitable."""
    url = payload.get(_ITUNES_URL_FIELD[ITUNES_ENTITY[kind]])
    if not url:
        return None
    artist = payload.get("artistName") or ""
    if kind == "artist":
        title = ""
    elif kind == "album":
        title = payload.get("collectionName") or ""
    else:
        title = payload.get("trackName") or ""
    return Candidate(PLATFORM_APPLE, kind, str(url), str(artist), str(title),
                     ident=str(payload.get("artistId" if kind == "artist"
                                            else "collectionId") or ""))


def search_query(reco: dict[str, Any], *, want_artist_page: bool) -> str:
    """Requête envoyée aux APIs : titre + artiste, ou le seul nom d'artiste."""
    if want_artist_page:
        return (reco.get("title") or "").strip()
    return f"{reco.get('title') or ''} {reco.get('creator') or ''}".strip()
