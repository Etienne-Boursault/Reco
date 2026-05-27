"""
enrich_music.py — Enrichit les recos musique/album/artiste avec leurs URLs
EXACTES sur Deezer et Spotify (deep links vers la fiche, pas une recherche).

Deezer : API publique, pas d'auth requise.
  - https://api.deezer.com/search/track?q=...
  - https://api.deezer.com/search/album?q=...
  - https://api.deezer.com/search/artist?q=...

Spotify : nécessite Client Credentials (https://developer.spotify.com/dashboard).
  - Échange un access_token côté serveur (cf. _spotify_token).
  - Endpoint /v1/search avec type=track,album,artist.

Pour chaque reco musique/album/artiste :
  1. Si type=album → recherche en album (Deezer + Spotify).
  2. Si type=artiste → recherche en artist.
  3. Si type=musique → essai track, puis album, puis artist (premier hit).
  4. Stocke externalIds.deezer / externalIds.spotify (URL canonique complète).

Usage :
    python enrich_music.py --source un-bon-moment [--limit N] [--force]
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from common import TOOLS_DIR, log, read_json, recos_dir_for, write_json_if_changed

DEEZER_BASE = "https://api.deezer.com"
SPOTIFY_BASE = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
RATE_LIMIT_SLEEP = 0.1


# ===== Deezer (pas d'auth) ================================================
def deezer_search(session: requests.Session, kind: str, query: str) -> dict | None:
    """Cherche sur Deezer. `kind` ∈ {'track', 'album', 'artist'}. Retourne le 1er
    résultat ou None."""
    url = f"{DEEZER_BASE}/search/{kind}"
    try:
        r = session.get(url, params={"q": query, "limit": 1}, timeout=15)
    except requests.RequestException as e:
        log.error("  Deezer HTTP : %s", e)
        return None
    if r.status_code != 200:
        return None
    results = (r.json() or {}).get("data") or []
    return results[0] if results else None


def deezer_url_for(reco_type: str, title: str, creator: str | None,
                   session: requests.Session) -> str | None:
    """Renvoie l'URL Deezer EXACTE du contenu, ou None."""
    q = f"{title} {creator}".strip() if creator else title
    # Stratégie de recherche selon le type RSS de la reco.
    kinds_to_try = (
        ["album"] if reco_type == "album"
        else ["artist"] if reco_type == "artiste"
        else ["track", "album", "artist"]
    )
    for kind in kinds_to_try:
        hit = deezer_search(session, kind, q)
        if hit and hit.get("link"):
            return hit["link"]
    return None


# ===== Spotify (Client Credentials) =======================================
def spotify_token(session: requests.Session, client_id: str, client_secret: str) -> str | None:
    """Récupère un access_token Spotify (Client Credentials flow). Le token expire
    après ~1h ; on le re-demande à chaque exécution du script — c'est rapide."""
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        r = session.post(
            SPOTIFY_TOKEN_URL,
            headers={"Authorization": f"Basic {auth}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
            timeout=15,
        )
    except requests.RequestException as e:
        log.error("Spotify token : %s", e)
        return None
    if r.status_code != 200:
        log.error("Spotify token HTTP %s : %s", r.status_code, r.text[:200])
        return None
    return (r.json() or {}).get("access_token")


def spotify_search(session: requests.Session, token: str, kind: str, query: str) -> dict | None:
    """Cherche sur Spotify. `kind` ∈ {'track', 'album', 'artist'}. Retourne le 1er
    résultat ou None."""
    try:
        r = session.get(
            f"{SPOTIFY_BASE}/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "type": kind, "limit": 1, "market": "FR"},
            timeout=15,
        )
    except requests.RequestException as e:
        log.error("  Spotify HTTP : %s", e)
        return None
    if r.status_code != 200:
        if r.status_code == 401:
            log.warning("  Spotify token invalide ou expiré")
        return None
    items = ((r.json() or {}).get(kind + "s") or {}).get("items") or []
    return items[0] if items else None


def spotify_url_for(reco_type: str, title: str, creator: str | None,
                    session: requests.Session, token: str) -> str | None:
    """Renvoie l'URL Spotify EXACTE, ou None."""
    q = f"{title} {creator}".strip() if creator else title
    kinds_to_try = (
        ["album"] if reco_type == "album"
        else ["artist"] if reco_type == "artiste"
        else ["track", "album", "artist"]
    )
    for kind in kinds_to_try:
        hit = spotify_search(session, token, kind, q)
        if hit:
            url = (hit.get("external_urls") or {}).get("spotify")
            if url:
                return url
    return None


# ===== Pipeline ==========================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true",
                        help="Re-traiter les recos déjà enrichies.")
    args = parser.parse_args()

    load_dotenv(TOOLS_DIR / ".env")
    spotify_id = os.getenv("SPOTIFY_CLIENT_ID")
    spotify_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    session = requests.Session()

    # Spotify : optionnel ET soumis à l'approbation « Extended Quota Mode »
    # depuis fin 2024 — sans approbation, /search renvoie HTTP 403 même avec
    # un token Client Credentials valide. On teste donc le token ET un appel
    # /search pour décider si Spotify est exploitable.
    token = None
    if spotify_id and spotify_secret:
        token = spotify_token(session, spotify_id, spotify_secret)
        if token:
            probe = session.get(
                f"{SPOTIFY_BASE}/search",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": "test", "type": "track", "limit": 1},
                timeout=15,
            )
            if probe.status_code == 200:
                log.info("Spotify : OK (token + /search autorisés).")
            else:
                log.warning(
                    "Spotify : token OK mais /search renvoie HTTP %s. "
                    "Probablement le mode développement par défaut depuis 2024 "
                    "(demande l'« Extended Quota Mode » sur le dashboard). "
                    "On continue avec Deezer seul.", probe.status_code,
                )
                token = None
        else:
            log.warning("Spotify : échec du token, on continue sans.")
    else:
        log.warning("Spotify : pas de SPOTIFY_CLIENT_ID/SECRET dans .env, "
                    "Deezer seul.")

    # Cibler les recos musique/album/artiste.
    target_types = {"musique", "album", "artiste"}
    recos_dir = recos_dir_for(args.source)
    targets = []
    for p in sorted(recos_dir.glob("*.json")):
        d = read_json(p)
        if d.get("type") not in target_types:
            continue
        ext = d.get("externalIds") or {}
        if not args.force and ext.get("deezer") and (not token or ext.get("spotify")):
            continue
        targets.append((p, d))
    if args.limit:
        targets = targets[: args.limit]
    log.info("%d reco(s) musique/album/artiste à enrichir.", len(targets))
    if not targets:
        return

    enriched = 0
    for i, (p, d) in enumerate(targets, 1):
        title = d["title"]
        creator = d.get("creator")
        reco_type = d["type"]
        log.info("[%d/%d] %s%s [%s]", i, len(targets), title[:50],
                 f" ({creator})" if creator else "", reco_type)
        ids = dict(d.get("externalIds") or {})
        changed = False

        if args.force or not ids.get("deezer"):
            url = deezer_url_for(reco_type, title, creator, session)
            if url:
                ids["deezer"] = url
                changed = True
                log.info("  Deezer  : %s", url)
            else:
                log.info("  Deezer  : pas trouvé")

        if token and (args.force or not ids.get("spotify")):
            url = spotify_url_for(reco_type, title, creator, session, token)
            if url:
                ids["spotify"] = url
                changed = True
                log.info("  Spotify : %s", url)
            else:
                log.info("  Spotify : pas trouvé")

        if changed:
            d["externalIds"] = ids
            if write_json_if_changed(p, d):
                enriched += 1
        time.sleep(RATE_LIMIT_SLEEP)

    log.info("Terminé : %d reco(s) enrichies.", enriched)


if __name__ == "__main__":
    main()
