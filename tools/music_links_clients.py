"""Clients HTTP Deezer, iTunes et Spotify — couche RÉSEAU.

Isolée pour être substituable en test : c'est la seule couche qui sort de la
machine, et la seule dont l'échec ne signifie pas « pas de correspondance »
mais « on n'a pas pu savoir ». La distinction compte, un 429 déguisé en
`no-match` faisant passer un problème d'infrastructure pour un refus de fond.

Extraite de `enrich_music_links.py` (cf. `music_links_matching`). Qobuz vit à
part (`music_links_qobuz`) : c'est du HTML et non une API.
"""
from __future__ import annotations

import base64
import os
import time
from typing import Any

import requests

from common import TOOLS_DIR, log
from music_links_matching import (
    DEEZER_BASE,
    HTTP_TIMEOUT,
    HTTP_TOO_MANY_REQUESTS,
    ITUNES_BASE,
    PLATFORM_APPLE,
    PLATFORM_DEEZER,
    PLATFORM_SPOTIFY,
    RETRY_AFTER_SLEEP,
    SEARCH_LIMIT,
    Candidate,
)

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_BASE = "https://api.spotify.com/v1"
#: Attribut posé sur la `Session` pour garder le jeton : (jeton, échéance).
#: Sur la session plutôt qu'en global — deux passes concurrentes ne partagent
#: alors rien, et un test fournit le jeton qu'il veut.
_SPOTIFY_CACHE_ATTR = "_reco_spotify_token"
#: Marge retirée à la durée de vie annoncée (3 600 s), pour ne pas présenter un
#: jeton expiré entre-temps.
_SPOTIFY_CACHE_MARGIN = 60.0


def get_json(session: requests.Session, url: str,
             params: dict[str, Any] | None = None,
             *, retries: int = 1,
             headers: dict[str, str] | None = None) -> dict[str, Any] | None:
    """GET → dict JSON, ou None en cas d'erreur réseau/HTTP/parse.

    Un HTTP 429 est réessayé après une pause (cf. `RETRY_AFTER_SLEEP`) : le
    confondre avec une absence de résultat fausserait le rapport.

    `headers` sert au jeton porteur de Spotify — les deux autres APIs sont
    publiques et n'en ont pas besoin.
    """
    try:
        resp = session.get(url, params=params, timeout=HTTP_TIMEOUT,
                           headers=headers)
    except requests.RequestException as exc:
        log.error("  HTTP %s : %s", url, exc)
        return None
    if resp.status_code == HTTP_TOO_MANY_REQUESTS and retries > 0:
        log.warning("  %s → HTTP 429, pause de %.0fs puis réessai",
                    url, RETRY_AFTER_SLEEP)
        time.sleep(RETRY_AFTER_SLEEP)
        return get_json(session, url, params, retries=retries - 1,
                        headers=headers)
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


def spotify_credentials() -> tuple[str, str] | None:
    """(client_id, client_secret) depuis l'environnement, ou None si absents.

    `tools/.env` est chargé paresseusement, comme dans `common` : le module
    s'importe sans secret, et une machine non configurée le dit clairement
    (`no-credentials`) au lieu de conclure à une absence sur Spotify.
    """
    from dotenv import load_dotenv
    load_dotenv(TOOLS_DIR / ".env")
    cid = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    return (cid, secret) if cid and secret else None


def spotify_token(session: requests.Session) -> str | None:
    """Jeton Client Credentials, mis en cache sur la session. None si échec.

    Le flux Client Credentials suffit : on ne lit que le catalogue public.
    """
    cache = getattr(session, _SPOTIFY_CACHE_ATTR, None)
    if cache and cache[1] > time.monotonic():
        return cache[0]
    identifiants = spotify_credentials()
    if identifiants is None:
        return None
    auth = base64.b64encode(":".join(identifiants).encode()).decode()
    try:
        resp = session.post(
            SPOTIFY_AUTH_URL, data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {auth}"}, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        log.error("  Spotify (jeton) : %s", exc)
        return None
    if resp.status_code != 200:
        log.error("  Spotify (jeton) → HTTP %s", resp.status_code)
        return None
    try:
        charge = resp.json()
    except ValueError:
        log.error("  Spotify (jeton) → réponse non-JSON")
        return None
    jeton = charge.get("access_token")
    if not jeton:
        return None
    duree = float(charge.get("expires_in") or 0) - _SPOTIFY_CACHE_MARGIN
    setattr(session, _SPOTIFY_CACHE_ATTR, (jeton, time.monotonic() + max(duree, 0)))
    return str(jeton)


def spotify_search(session: requests.Session, kind: str,
                   query: str) -> list[dict[str, Any]]:
    """Recherche Spotify. Liste vide en cas d'erreur ou de réponse vide.

    Un HTTP 403 est attendu le jour où l'abonnement du compte expire (il court
    jusqu'à la mi-octobre 2026) : il passe alors par `get_json`, qui journalise
    et rend None — aucune exception, et les autres plateformes continuent.
    """
    jeton = spotify_token(session)
    if not jeton:
        return []
    data = get_json(session, f"{SPOTIFY_BASE}/search",
                    {"q": query, "type": kind, "market": "FR",
                     "limit": SEARCH_LIMIT},
                    headers={"Authorization": f"Bearer {jeton}"})
    if not data:
        return []
    results = (data.get(f"{kind}s") or {}).get("items")
    return [r for r in results if isinstance(r, dict)] if isinstance(results, list) else []


def spotify_candidate(payload: dict[str, Any], kind: str) -> Candidate | None:
    """Convertit un résultat Spotify en `Candidate`. None si inexploitable."""
    url = (payload.get("external_urls") or {}).get("spotify")
    if not url:
        return None
    if kind == "artist":
        artist, title = payload.get("name") or "", ""
    else:
        # L'artiste PRINCIPAL seulement, comme Deezer (`artist.name`) et iTunes
        # (`artistName`) : concaténer les invités (« Ben Mazué, Yoa ») ferait
        # dériver la comparaison de noms, dont le seuil est calibré sur un nom.
        artistes = [a.get("name") for a in (payload.get("artists") or [])
                    if isinstance(a, dict) and a.get("name")]
        artist = str(artistes[0]) if artistes else ""
        title = payload.get("name") or ""
    return Candidate(PLATFORM_SPOTIFY, kind, str(url), str(artist), str(title),
                     ident=str(payload.get("id") or ""))


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
