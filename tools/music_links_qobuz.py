"""Client Qobuz — couche RÉSEAU, isolée parce que c'est du HTML, pas une API.

Qobuz n'expose pas d'API publique sans identifiant d'application. On passe donc
par sa recherche web, et c'est la SEULE source de ce dépôt qui repose sur la
structure d'une page. Isolée ici pour que sa fragilité soit visible et qu'elle
puisse être retirée sans toucher aux autres plateformes : si Qobuz change son
HTML, cette passe cesse de trouver des liens (raison `no-match` ou
`http-error`) mais n'écrit jamais rien de faux et ne gêne pas Deezer, Apple
Music ni Spotify.

CE QUE LA PAGE DONNE (vérifié le 2026-09-25)
--------------------------------------------
  - Recherche : `/fr-fr/search?q=…` rend des chemins `/fr-fr/album/<slug>/<id>`
    et `/fr-fr/interpreter/<slug>/<id>`. Une recherche sans résultat pertinent
    rend les chemins d'AUTRES artistes (« Mona Guba » → amparo-sanchez) : le
    chemin ne prouve donc rien, il faut ouvrir la page.
  - Page album : JSON-LD `{"@type":"Product","name":…,"brand":{"name":…}}` →
    titre de l'album ET nom de l'artiste, les deux données dont la
    corroboration a besoin.
  - Pistes d'un album : `<div class="track__item track__item--name"
    itemprop="name"><span>…</span></div>`, doublées d'un `item_name` dans le
    `data-track-v2` d'analytique. On lit les deux : le premier porte parfois un
    suffixe (« Gitana Te Quiero (Bulerías) ») que le second n'a pas.
  - Page interprète : pas de JSON-LD exploitable, mais un titre de la forme
    « Discographie de <nom> - … ».

Aucune URL n'est fabriquée : celles qu'on renvoie ont toutes été lues dans une
page de Qobuz, puis corroborées par le contenu de la page cible.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any

import requests

from common import log, normalize_text
from music_links_matching import (
    HTTP_TIMEOUT,
    PLATFORM_QOBUZ,
    Candidate,
)

QOBUZ_BASE = "https://www.qobuz.com/fr-fr"
#: Nombre maximum de pages ouvertes par reco. Une page Qobuz pèse ~300 Ko :
#: au-delà de trois candidats, le coût dépasse le gain.
MAX_PAGES = 3
#: Un navigateur est attendu : sans `User-Agent`, la recherche répond 403.
_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "fr"}

_RE_ALBUM_PATH = re.compile(r"/fr-fr/album/[a-z0-9-]+/[a-z0-9]+", re.IGNORECASE)
_RE_ARTIST_PATH = re.compile(r"/fr-fr/interpreter/[a-z0-9-]+/\d+", re.IGNORECASE)
_RE_JSON_LD = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.DOTALL)
_RE_TRACK_NAME = re.compile(
    r'class="track__item track__item--name"[^>]*>\s*<span>([^<]+)</span>')
_RE_TRACK_ITEM_NAME = re.compile(r"&quot;item_name&quot;:&quot;([^&]+)&quot;")
_RE_TITLE = re.compile(r"<title>([^<]*)", re.IGNORECASE)
_RE_DISCOGRAPHIE = re.compile(r"discographie de\s+(.+?)\s+-\s", re.IGNORECASE)

#: Chemins cherchés selon le type de contenu visé. Un morceau n'a pas de page
#: dédiée exploitable chez Qobuz : on vise l'album qui le porte, comme le fait
#: déjà le corpus (le lien Qobuz de « Une autre histoire d'amour » pointe sur
#: l'album « Qu'en restera-t-il »).
_PATH_PATTERN = {"album": _RE_ALBUM_PATH, "track": _RE_ALBUM_PATH,
                 "artist": _RE_ARTIST_PATH}


def _get_html(session: requests.Session, url: str) -> str | None:
    """GET → HTML, ou None sur erreur réseau/HTTP. Ne lève jamais."""
    try:
        resp = session.get(url, timeout=HTTP_TIMEOUT, headers=_HEADERS)
    except requests.RequestException as exc:
        log.error("  Qobuz %s : %s", url, exc)
        return None
    if resp.status_code != 200:
        log.error("  Qobuz %s → HTTP %s", url, resp.status_code)
        return None
    return resp.text


def search_paths(session: requests.Session, kind: str,
                 query: str) -> list[str]:
    """URLs candidates RENVOYÉES par la recherche Qobuz, dans l'ordre, sans doublon."""
    page = _get_html(session, f"{QOBUZ_BASE}/search?q={requests.utils.quote(query)}")
    if not page:
        return []
    vus: list[str] = []
    for m in _PATH_PATTERN[kind].finditer(page):
        url = "https://www.qobuz.com" + m.group(0)
        if url not in vus:
            vus.append(url)
    return vus[:MAX_PAGES]


def _json_ld(page: str) -> list[dict[str, Any]]:
    """Objets JSON-LD de la page, à plat. Un bloc illisible est ignoré."""
    objets: list[dict[str, Any]] = []
    for bloc in _RE_JSON_LD.findall(page):
        try:
            donnees = json.loads(bloc.strip())
        except ValueError:
            continue
        for obj in (donnees if isinstance(donnees, list) else [donnees]):
            if isinstance(obj, dict):
                objets.append(obj)
    return objets


def album_identity(page: str) -> tuple[str, str]:
    """(titre, artiste) d'une page album, d'après son JSON-LD. Vides si absent."""
    for obj in _json_ld(page):
        if obj.get("@type") != "Product":
            continue
        marque = obj.get("brand")
        artiste = marque.get("name") if isinstance(marque, dict) else None
        if obj.get("name") and artiste:
            return str(obj["name"]), str(artiste)
    return "", ""


def artist_identity(page: str) -> str:
    """Nom porté par une page interprète, ou chaîne vide.

    Le JSON-LD d'une page interprète ne porte pas le nom : on lit le titre de la
    page, de la forme « Discographie de <nom> - … ».
    """
    for obj in _json_ld(page):
        if obj.get("@type") in ("MusicGroup", "Person") and obj.get("name"):
            return str(obj["name"])
    titre = _RE_TITLE.search(page)
    if not titre:
        return ""
    trouve = _RE_DISCOGRAPHIE.search(html.unescape(titre.group(1)))
    return trouve.group(1).strip() if trouve else ""


def track_names(page: str) -> list[str]:
    """Titres des pistes listées par une page album (les deux balisages)."""
    noms = [html.unescape(n).strip() for n in _RE_TRACK_NAME.findall(page)]
    noms += [html.unescape(n).strip() for n in _RE_TRACK_ITEM_NAME.findall(page)]
    return [n for n in noms if n]


def _ident(url: str) -> str:
    """Identifiant Qobuz porté par l'URL (dernier segment)."""
    return url.rstrip("/").rsplit("/", 1)[-1]


def candidates(session: requests.Session, kind: str, query: str,
               wanted_title: str | None = None) -> list[Candidate]:
    """Candidats Qobuz corroborés PAR LEUR PAGE, prêts pour les garde-fous.

    Chaque candidat porte ce que la page affirme (titre + artiste), jamais ce
    qu'on cherchait : c'est `verdict()` qui tranche ensuite, avec les mêmes
    règles que pour Deezer et Apple Music.

    Pour un morceau, la page visée est celle de l'album : le candidat n'est
    construit que si l'album liste VRAIMENT une piste au titre cherché, et il
    porte alors ce titre de piste.
    """
    trouves: list[Candidate] = []
    for url in search_paths(session, kind, query):
        page = _get_html(session, url)
        if not page:
            continue
        if kind == "artist":
            nom = artist_identity(page)
            if nom:
                trouves.append(Candidate(PLATFORM_QOBUZ, kind, url, nom,
                                         ident=_ident(url)))
            continue
        titre, artiste = album_identity(page)
        if not titre or not artiste:
            continue
        if kind == "album":
            trouves.append(Candidate(PLATFORM_QOBUZ, kind, url, artiste, titre,
                                     ident=_ident(url)))
            continue
        cible = normalize_text(wanted_title)
        piste = next((n for n in track_names(page)
                      if cible and normalize_text(n) == cible), None)
        if piste:
            trouves.append(Candidate(PLATFORM_QOBUZ, kind, url, artiste, piste,
                                     ident=_ident(url)))
    return trouves
