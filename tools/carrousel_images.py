"""
carrousel_images.py — l'image de chaque page du carrousel d'un episode.

Demande d'Etienne du 2026-11-13 (« recuperer des visuels pour le carrousel ?
Genre les pochettes d'album, de film »), modele valide le meme jour sur le
canevas Design « Carrousel avec visuels » (S6-E09, premier carrousel publie
avec visuels).

L'image vient des identifiants deja verifies sur la reco, jamais d'une
recherche par titre :
- film, serie : l'affiche TMDB dans la langue originale de l'oeuvre (Etienne a
  prefere l'affiche originale d'Eternal Sunshine a l'affiche francaise) ;
- album : la pochette Deezer, sinon Apple Music ;
- artiste, musique : la photo Deezer (pas la photo grise par defaut) ;
- podcast : la vignette Apple Podcasts ;
- chaine : l'avatar YouTube ;
- livre, BD : l'image de l'article Wikipedia ;
- sinon : l'image de partage (og:image) du site officiel.
Une source qui ne repond pas ne donne rien : la page reste sans image, et
l'editeur peut toujours poser ou retirer une image a la main dans
`episode.json` (une photo d'artiste Deezer peut etre une pochette de single
inutilisable, vu pour Adele Castillon).
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any, Protocol
from urllib.parse import urljoin

log = logging.getLogger("reco")

TMDB = "https://api.themoviedb.org/3"
AFFICHE = "https://image.tmdb.org/t/p/w780"
ITUNES = "https://itunes.apple.com/lookup"
RONDS = {"Artiste", "Chaîne YouTube", "Musique"}


class Web(Protocol):
    def json(self, url: str, **params: Any) -> dict[str, Any]: ...
    def html(self, url: str) -> str: ...
    def avatar_youtube(self, url: str) -> str | None: ...


NAVIGATEUR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36",
              "Accept-Language": "fr-FR,fr;q=0.9"}
OUTIL = "UneBonneReco/1.0 (carrousel des recos ; https://unebonnere.co)"


class WebReel:
    """Acces reel au web : APIs publiques (requests), avatar YouTube (yt-dlp)."""

    def __init__(self, session: Any = None, ytdl: Any = None) -> None:
        if session is None:  # pragma: no cover — la session reelle, remplacee dans les tests
            import requests
            session = requests.Session()
        self._session, self._ytdl = session, ytdl

    def json(self, url: str, **params: Any) -> dict[str, Any]:
        # Wikimedia refuse (403) un agent qui imite un navigateur : il veut le nom de l'outil.
        entetes = {**NAVIGATEUR, "User-Agent": OUTIL} if "wikipedia.org" in url else NAVIGATEUR
        reponse = self._session.get(url, params=params or None, headers=entetes, timeout=20)
        reponse.raise_for_status()
        return reponse.json()

    def html(self, url: str) -> str:
        # SOCS=CAI : sans lui, YouTube et Google rendent leur page de consentement.
        reponse = self._session.get(url, headers={**NAVIGATEUR, "Cookie": "SOCS=CAI"}, timeout=20)
        reponse.raise_for_status()
        return reponse.text

    def avatar_youtube(self, url: str) -> str | None:
        infos = self._ytdl(url) if self._ytdl else self._yt_dlp(url)
        return next((t["url"] for t in infos.get("thumbnails") or [] if t.get("id") == "avatar_uncropped"), None)

    @staticmethod
    def _yt_dlp(url: str) -> dict[str, Any]:
        import yt_dlp
        options = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlist_items": "0"}
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False)


def _liens(reco: dict[str, Any]) -> list[dict[str, Any]]:
    return [lien for lien in reco.get("links") or [] if lien.get("url")]


def _premier(reco: dict[str, Any], motif: str) -> re.Match[str] | None:
    return next((m for lien in _liens(reco) if (m := re.search(motif, lien["url"]))), None)


def _affiche(item: dict[str, Any], reco: dict[str, Any], web: Web, cle: str | None) -> str | None:
    ids = {**(item.get("externalIds") or {}), **(reco.get("externalIds") or {})}
    if not (cle and ids.get("tmdb")):
        return None
    base = f"{TMDB}/{ids.get('tmdbType') or 'movie'}/{ids['tmdb']}"
    langue = web.json(base, api_key=cle).get("original_language")
    affiches = web.json(base + "/images", api_key=cle).get("posters") or []
    choisie = next((a for a in affiches if a.get("iso_639_1") == langue), affiches[0] if affiches else None)
    return AFFICHE + choisie["file_path"] if choisie else None


def _pochette(reco: dict[str, Any], web: Web) -> str | None:
    if m := _premier(reco, r"deezer\.com/(?:\w+/)?album/(\d+)"):
        return web.json(f"https://api.deezer.com/album/{m[1]}").get("cover_xl")
    if m := _premier(reco, r"music\.apple\.com/.*/album/[^/]+/(\d+)"):
        resultats = web.json(ITUNES, id=m[1], country="fr").get("results") or []
        if resultats and resultats[0].get("artworkUrl100"):
            return resultats[0]["artworkUrl100"].replace("100x100", "1000x1000")
    return None


def _photo_artiste(reco: dict[str, Any], web: Web) -> str | None:
    if m := _premier(reco, r"deezer\.com/(?:\w+/)?artist/(\d+)"):
        photo = web.json(f"https://api.deezer.com/artist/{m[1]}").get("picture_xl")
        return photo if photo and "/artist//" not in photo else None
    return None


def _vignette_podcast(reco: dict[str, Any], web: Web) -> str | None:
    if m := _premier(reco, r"podcasts\.apple\.com/.*/id(\d+)"):
        resultats = web.json(ITUNES, id=m[1], country="fr").get("results") or []
        if resultats and resultats[0].get("artworkUrl600"):
            return resultats[0]["artworkUrl600"].replace("600x600", "1200x1200")
    return None


def _avatar(reco: dict[str, Any], web: Web) -> str | None:
    m = _premier(reco, r"https://www\.youtube\.com/(?:@[\w.-]+|channel/[\w-]+)")
    return web.avatar_youtube(m[0]) if m else None


def _wikipedia(reco: dict[str, Any], web: Web) -> str | None:
    if m := _premier(reco, r"fr\.wikipedia\.org/wiki/([^?#]+)"):
        page = web.json(f"https://fr.wikipedia.org/api/rest_v1/page/summary/{m[1]}")
        return (page.get("originalimage") or {}).get("source")
    return None


def _partage(reco: dict[str, Any], web: Web) -> str | None:
    officiel = next((lien["url"] for lien in _liens(reco) if lien.get("kind") == "official"), None)
    if not officiel:
        return None
    page = web.html(officiel)
    if m := re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', page):
        return html.unescape(m[1])
    # Pas d'image de partage : l'icone d'application du site, a defaut (WikiMasters).
    if m := re.search(r'<link[^>]+rel="apple-touch-icon"[^>]+href="([^"]+)"', page):
        return urljoin(officiel, html.unescape(m[1]))
    return None


def source(item: dict[str, Any], reco: dict[str, Any], web: Web, cle_tmdb: str | None) -> str | None:
    """Adresse de l'image d'une page, ou None (page sans image)."""
    types = set(reco.get("types") or item.get("types") or [])
    essais = []
    if types & {"film", "serie"}:
        essais.append(lambda: _affiche(item, reco, web, cle_tmdb))
    if "album" in types:
        essais.append(lambda: _pochette(reco, web))
    if types & {"artiste", "musique"}:
        essais.append(lambda: _photo_artiste(reco, web))
    if "podcast" in types:
        essais.append(lambda: _vignette_podcast(reco, web))
    if "chaine" in types:
        essais.append(lambda: _avatar(reco, web))
    if types & {"livre", "bd"}:
        essais.append(lambda: _wikipedia(reco, web))
    essais.append(lambda: _partage(reco, web))
    for essai in essais:
        try:
            if url := essai():
                return url
        # Une source en panne (reseau, reponse inattendue) ne bloque pas le carrousel.
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            log.warning("image du carrousel : source en echec pour %s (%s : %s)",
                        reco.get("id", "?"), type(exc).__name__, exc)
    return None


def couverture(guid: str) -> str | None:
    """Vignette YouTube de l'episode (guid « yt-<id> »)."""
    return f"https://i.ytimg.com/vi/{guid[3:]}/maxresdefault.jpg" if guid.startswith("yt-") else None


def mise_en_scene(type_: str, tailles: list[tuple[int, int]]) -> str:
    """Mise en scene d'une page d'apres son type et les proportions de ses images."""
    if not tailles:
        return "sans"
    if len(tailles) > 1:
        return "double"
    largeur, hauteur = tailles[0]
    if largeur <= 300 and hauteur <= 300:
        return "tuile"
    rapport = hauteur / largeur
    if rapport >= 1.2:
        return "affiche"
    if rapport <= 0.85:
        return "photo" if largeur >= 800 else "cadre"
    return "rond" if type_ in RONDS else "carre"


CREDITS = (("image.tmdb.org", "affiches TMDB"), ("dzcdn.net", "pochettes Deezer"),
           ("mzstatic.com", "Apple"), ("ytimg.com", "YouTube"), ("googleusercontent.com", "YouTube"),
           ("wikimedia.org", "Wikipédia"))


def credits(urls: list[str]) -> str:
    """Ligne de la page de fin qui nomme les sources des images."""
    noms: list[str] = []
    for url in urls:
        nom = next((n for domaine, n in CREDITS if domaine in url), "sites des œuvres")
        if nom not in noms:
            noms.append(nom)
    if "sites des œuvres" in noms:
        noms.append(noms.pop(noms.index("sites des œuvres")))
    return "Images : " + ", ".join(noms) if noms else ""
