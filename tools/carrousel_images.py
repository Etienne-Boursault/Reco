"""
carrousel_images.py — l'image de chaque page du carrousel d'un épisode.

Demande d'Étienne du 2026-11-13 (« récupérer des visuels pour le carrousel ?
Genre les pochettes d'album, de film »), modèle validé le même jour sur le
canevas Design « Carrousel avec visuels » (S6-E09, premier carrousel publié
avec visuels).

L'image vient des identifiants déjà vérifiés sur la reco, jamais d'une
recherche par titre :
- film, série : l'affiche TMDB dans la langue originale de l'œuvre (Étienne a
  préféré l'affiche originale d'Eternal Sunshine à l'affiche française), à
  défaut la française, puis une affiche sans texte ;
- album : la pochette Deezer, sinon Apple Music ;
- artiste, musique : la photo Deezer (pas la photo grise par défaut) ;
- podcast : la vignette Apple Podcasts ;
- chaîne : l'avatar YouTube ;
- livre, BD : l'image de l'article Wikipédia, sinon celle de la librairie ;
- sinon : l'image de partage (og:image) du site officiel, ou son icône.
Une source qui ne répond pas ne donne rien : la page reste sans image, et
l'éditeur peut toujours poser ou retirer une image à la main dans
`episode.json` (une photo d'artiste Deezer peut être une pochette de single
inutilisable, vu pour Adèle Castillon).
"""
from __future__ import annotations

import html
import logging
import re
import sys
import threading
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, unquote, urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from link_check import BROWSER_HEADERS

log = logging.getLogger("reco")

TMDB = "https://api.themoviedb.org/3"
AFFICHE = "https://image.tmdb.org/t/p/w780"
ITUNES = "https://itunes.apple.com/lookup"
#: Types dont l'image est le portrait d'une personne ou l'avatar d'une chaîne : en rond.
RONDS = {"Artiste", "Chaîne YouTube"}
#: Adresses de photos d'artiste et d'avatars : en rond aussi, quel que soit le type de la page
#: (une page « Musique » peut porter la photo de l'artiste ou la pochette de son album).
PORTRAITS = ("/images/artist/", "yt3.googleusercontent.com", "yt3.ggpht.com")
#: En-têtes d'un navigateur, ceux de link_check, sans le cookie de consentement (API, images).
NAVIGATEUR = {cle: valeur for cle, valeur in BROWSER_HEADERS.items() if cle not in ("Cookie", "Accept")}
OUTIL = "UneBonneReco/1.0 (carrousel des recos ; https://unebonnere.co)"
#: Wikimedia (API, pages et serveur d'images) refuse (403) un agent qui imite un navigateur.
WIKIMEDIA = ("wikipedia.org", "wikimedia.org")
#: Une balise og:image est dans l'en-tête : inutile de lire plus loin.
TAILLE_PAGE = 512_000
#: Ce qu'une source en panne peut lever : réseau, réponse de forme inattendue (clé, index,
#: encodage inconnu), module absent. Une erreur de programmation (TypeError,
#: AttributeError) remonte, au lieu de passer pour une source en panne.
PANNES = (OSError, ValueError, LookupError, ImportError)
#: Palier de vignette standard de Wikimedia : d'autres largeurs peuvent être refusées.
VIGNETTE_WIKIMEDIA = 960
#: Types de contenu d'une image servie sans le bon type (S3, CDN) : Pillow tranchera au rendu.
BINAIRES = ("application/octet-stream", "binary/octet-stream")
#: Ce qu'Edge affiche à coup sûr (pas de TIFF, de HEIC ni d'ICO, que Pillow lit pourtant).
AFFICHABLES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}


def entetes(url: str) -> dict[str, str]:
    """En-têtes d'une requête vers `url` : l'agent de l'outil pour Wikimedia, un navigateur ailleurs."""
    return {**NAVIGATEUR, "User-Agent": OUTIL} if any(d in url for d in WIKIMEDIA) else dict(NAVIGATEUR)


def _objet(valeur: Any) -> dict[str, Any]:
    """Une réponse d'API attendue comme objet ; une liste ou un null deviennent un objet vide."""
    return valeur if isinstance(valeur, dict) else {}


class Web(Protocol):
    def json(self, url: str, **params: Any) -> dict[str, Any]: ...
    def html(self, url: str) -> tuple[str, str]: ...
    def avatar_youtube(self, url: str) -> str | None: ...
    def image_valide(self, url: str) -> bool: ...


class WebReel:
    """Accès réel au web : APIs publiques (requests), avatar YouTube (yt-dlp)."""

    def __init__(self, session: Any = None, ytdl: Any = None, fabrique: Any = None) -> None:
        """`session` : une seule pour tous (tests) ; sinon une par fil, créée par `fabrique`,
        car une requests.Session n'est pas garantie sûre entre les fils de la préparation."""
        self._unique, self._ytdl, self._fabrique = session, ytdl, fabrique
        self._local = threading.local()

    @property
    def _session(self) -> Any:
        if self._unique is not None:
            return self._unique
        if not hasattr(self._local, "session"):
            self._local.session = self._fabrique() if self._fabrique else _session_requests()
        return self._local.session

    def json(self, url: str, **params: Any) -> dict[str, Any]:
        reponse = self._session.get(url, params=params or None, headers=entetes(url), timeout=20)
        reponse.raise_for_status()
        return _objet(reponse.json())

    def html(self, url: str) -> tuple[str, str]:
        """(adresse finale après redirections, début de la page)."""
        # BROWSER_HEADERS porte SOCS=CAI : sans lui, YouTube et Google rendent leur consentement.
        en_tetes = entetes(url) if any(d in url for d in WIKIMEDIA) else BROWSER_HEADERS
        reponse = self._session.get(url, headers=en_tetes, timeout=20, stream=True)
        try:
            reponse.raise_for_status()
            lu = b""
            for morceau in reponse.iter_content(chunk_size=65_536):
                lu += morceau
                if len(lu) >= TAILLE_PAGE:
                    break
            return reponse.url or url, _decoder(lu[:TAILLE_PAGE], reponse.encoding)
        finally:
            reponse.close()

    def image_valide(self, url: str) -> bool:
        """L'adresse rend-elle une image que Pillow et Edge savent afficher (pas un SVG, pas du HTML) ?"""
        try:
            reponse = self._session.get(url, headers=entetes(url), timeout=20, stream=True)
        except OSError as exc:
            log.warning("image du carrousel : %s injoignable (%s)", _sans_secret(url), type(exc).__name__)
            return False
        try:
            genre = (reponse.headers.get("content-type") or "").split(";")[0].strip().lower()
            return reponse.status_code == 200 and (genre in AFFICHABLES or genre in BINAIRES)
        finally:
            reponse.close()

    def avatar_youtube(self, url: str) -> str | None:
        infos = self._ytdl(url) if self._ytdl else self._yt_dlp(url)
        return next((t["url"] for t in infos.get("thumbnails") or [] if t.get("id") == "avatar_uncropped"), None)

    @staticmethod
    def _yt_dlp(url: str) -> dict[str, Any]:
        import yt_dlp
        options = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlist_items": "0"}
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(url, download=False)
        except yt_dlp.utils.YoutubeDLError as exc:  # chaîne supprimée, privée, connexion exigée
            log.warning("image du carrousel : pas d'avatar pour %s (%s)", url, exc)
            return {}


def _session_requests() -> Any:  # pragma: no cover — la session réelle, remplacée dans les tests
    import requests
    return requests.Session()


def _decoder(octets: bytes, encodage: str | None) -> str:
    """Décode une page : l'encodage annoncé s'il est connu ; sans annonce (requests suppose
    alors ISO-8859-1), UTF-8 d'abord, Latin-1 à défaut."""
    if encodage and encodage.lower() not in ("iso-8859-1", "latin-1"):
        try:
            return octets.decode(encodage, errors="replace")
        except LookupError:  # « utf8mb4 », « none » : un encodage que Python ne connaît pas
            pass
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError as exc:
        if exc.start >= len(octets) - 3:  # coupure au milieu du dernier caractère : c'est de l'UTF-8
            return octets[:exc.start].decode("utf-8", errors="replace")
        return octets.decode("latin-1")


def _liens(reco: dict[str, Any]) -> list[dict[str, Any]]:
    return [lien for lien in reco.get("links") or [] if lien.get("url")]


def _premier(reco: dict[str, Any], motif: str) -> re.Match[str] | None:
    return next((m for lien in _liens(reco) if (m := re.search(motif, lien["url"]))), None)


def _affiche(item: dict[str, Any], reco: dict[str, Any], web: Web, cle: str | None) -> str | None:
    # Identifiant et type d'une même source (la reco, sinon la fiche), jamais un couple croisé ;
    # sans type, rien : les identifiants des films et des séries se chevauchent.
    ids = next((d for d in (reco.get("externalIds") or {}, item.get("externalIds") or {}) if d.get("tmdb")), {})
    if not (cle and ids.get("tmdb") and ids.get("tmdbType") in ("movie", "tv")):
        return None
    base = f"{TMDB}/{ids['tmdbType']}/{ids['tmdb']}"
    langue = _objet(web.json(base, api_key=cle)).get("original_language")
    affiches = [a for a in _objet(web.json(base + "/images", api_key=cle)).get("posters") or []
                if isinstance(a, dict) and a.get("file_path")]
    for voulue in (langue, "fr", None):  # langue originale, française, sans texte
        if choisie := next((a for a in affiches if a.get("iso_639_1") == voulue), None):
            return AFFICHE + choisie["file_path"]
    return AFFICHE + affiches[0]["file_path"] if affiches else None


def _pochette(reco: dict[str, Any], web: Web) -> str | None:
    """Pochette d'un album, ou de l'album d'un titre."""
    pochette = None
    if m := _premier(reco, r"deezer\.com/(?:\w+/)?album/(\d+)"):
        pochette = _objet(web.json(f"https://api.deezer.com/album/{m[1]}")).get("cover_xl")
    elif m := _premier(reco, r"deezer\.com/(?:\w+/)?track/(\d+)"):
        pochette = _objet(_objet(web.json(f"https://api.deezer.com/track/{m[1]}")).get("album")).get("cover_xl")
    if pochette and "/cover//" not in pochette:  # « /cover// » : la pochette grise par défaut
        return pochette
    # Avec ou sans le nom de l'album dans l'adresse (liens courts « /album/<id> »).
    if m := _premier(reco, r"music\.apple\.com/.*/album/(?:[^/?]+/)?(\d+)"):
        return _artwork_itunes(m[1], web, "artworkUrl100", "100x100", "1000x1000")
    return None


def _artwork_itunes(identifiant: str, web: Web, champ: str, petite: str, grande: str) -> str | None:
    """Image agrandie d'un album ou d'un podcast Apple, par la recherche iTunes."""
    resultat = _objet((_objet(web.json(ITUNES, id=identifiant, country="fr")).get("results") or [{}])[0])
    return resultat[champ].replace(petite, grande) if resultat.get(champ) else None


def _photo_artiste(reco: dict[str, Any], web: Web) -> str | None:
    if m := _premier(reco, r"deezer\.com/(?:\w+/)?artist/(\d+)"):
        photo = _objet(web.json(f"https://api.deezer.com/artist/{m[1]}")).get("picture_xl")
        return photo if photo and "/artist//" not in photo else None
    return None


def _vignette_podcast(reco: dict[str, Any], web: Web) -> str | None:
    if m := _premier(reco, r"podcasts\.apple\.com/.*/id(\d+)"):
        return _artwork_itunes(m[1], web, "artworkUrl600", "600x600", "1200x1200")
    return None


def _avatar(reco: dict[str, Any], web: Web) -> str | None:
    m = _premier(reco, r"(?:https?://)?(?:www\.|m\.)?youtube\.com/(@[\w.%-]+|(?:channel|c|user)/[\w.%-]+)")
    return web.avatar_youtube(f"https://www.youtube.com/{m[1]}") if m else None


def _wikipedia(reco: dict[str, Any], web: Web) -> str | None:
    if m := _premier(reco, r"fr\.wikipedia\.org/wiki/([^?#]+)"):
        titre = quote(unquote(m[1]), safe="")  # « AC/DC » : la barre fait partie du titre
        page = _objet(web.json(f"https://fr.wikipedia.org/api/rest_v1/page/summary/{titre}"))
        original = _objet(page.get("originalimage"))
        vignette = _objet(page.get("thumbnail")).get("source")
        largeur = original.get("width") or 0
        # L'extension se lit dans le chemin : Wikipédia ajoute « ?utm_source=… » à l'adresse.
        lisible = re.search(r"\.(jpe?g|png|webp|gif)$", urlparse(original.get("source") or "").path, re.IGNORECASE)
        # Un original lisible de moins de 1 000 px se prend tel quel. Sinon la vignette, que
        # Wikimedia rend en JPEG ou PNG : agrandie au palier standard de 960 px seulement si
        # l'original est au moins aussi large (Wikimedia refuse d'agrandir, HTTP 400).
        if lisible and largeur and largeur <= 1000:
            return original["source"]
        if vignette:
            return re.sub(r"/\d+px-", f"/{VIGNETTE_WIKIMEDIA}px-", vignette) if largeur >= VIGNETTE_WIKIMEDIA \
                else vignette
        return original.get("source")
    return None


def _attributs(balise: str) -> dict[str, str]:
    return {nom.lower(): html.unescape(valeur) for nom, _, valeur in re.findall(r"([\w:-]+)\s*=\s*([\"'])(.*?)\2", balise)}


def _image_de_page(url: str, web: Web) -> str | None:
    """og:image de la page (quel que soit l'ordre des attributs), sinon son icône d'application.
    Une adresse relative se résout sur l'adresse finale, après redirections."""
    url, page = web.html(url)
    for balise in re.findall(r"<meta\b[^>]*>", page, flags=re.IGNORECASE):
        attrs = _attributs(balise)
        noms = {attrs.get("property"), attrs.get("name")}
        if noms & {"og:image", "og:image:url", "og:image:secure_url"} and attrs.get("content"):
            return urljoin(url, attrs["content"])
    for balise in re.findall(r"<link\b[^>]*>", page, flags=re.IGNORECASE):
        attrs = _attributs(balise)
        rel = (attrs.get("rel") or "").lower().split()
        # WikiMasters n'a que celle-ci ; « -precomposed » sur les vieux CMS.
        if {"apple-touch-icon", "apple-touch-icon-precomposed"} & set(rel) and attrs.get("href"):
            return urljoin(url, attrs["href"])
    return None


#: Une page de recherche de librairie porte le logo du site, pas la couverture d'un livre.
#: Un segment de chemin (« /recherche », « /search/… », « listeliv.php ») ou un paramètre de
#: requête, jamais un mot du titre (« /a-la-recherche-du-temps-perdu »).
RECHERCHE = re.compile(r"(?:/(?:recherche|search|listeliv[^/?]*)(?:[/?]|$))|[?&](?:q|query|mots?|mots_recherche|term)=",
                       re.IGNORECASE)


def _partage(reco: dict[str, Any], web: Web, genres: tuple[str, ...] = ("official",),
             sauf_recherche: bool = False) -> str | None:
    lien = next((lien["url"] for lien in _liens(reco)
                 if lien.get("kind") in genres and not (sauf_recherche and RECHERCHE.search(lien["url"]))), None)
    return _image_de_page(lien, web) if lien else None


def _sans_secret(texte: str) -> str:
    """Retire la clé TMDB d'un message d'erreur (elle voyage dans l'adresse)."""
    return re.sub(r"api_key=[^&\s)'\"]+", "api_key=…", texte)


def source(item: dict[str, Any], reco: dict[str, Any], web: Web, cle_tmdb: str | None) -> str | None:
    """Adresse de l'image d'une page, ou None (page sans image)."""
    # Les types de la fiche d'abord, comme le libellé de la page (reseaux_episode.carrousel) ;
    # ceux de la reco seulement si la fiche n'en a pas.
    types = set(item.get("types") or reco.get("types") or [])
    essais = []
    if types & {"film", "serie"}:
        essais.append(lambda: _affiche(item, reco, web, cle_tmdb))
    if types & {"album", "musique"}:
        essais.append(lambda: _pochette(reco, web))
    if types & {"artiste", "musique"}:
        essais.append(lambda: _photo_artiste(reco, web))
    if "podcast" in types:
        essais.append(lambda: _vignette_podcast(reco, web))
    if "chaine" in types:
        essais.append(lambda: _avatar(reco, web))
    if types & {"livre", "bd"}:
        essais += [lambda: _wikipedia(reco, web), lambda: _partage(reco, web, ("buy",), sauf_recherche=True)]
    essais.append(lambda: _partage(reco, web))
    for essai in essais:
        try:
            # Une adresse qui ne rend pas d'image affichable laisse sa chance à la source suivante.
            if (url := essai()) and web.image_valide(url):
                return url
        except PANNES as exc:  # une source en panne ne bloque pas le carrousel
            log.warning("image du carrousel : source en échec pour %s (%s : %s)",
                        reco.get("id", "?"), type(exc).__name__, _sans_secret(str(exc)))
    return None


def couverture(ep: dict[str, Any]) -> str | None:
    """Vignette YouTube de l'épisode : son adresse YouTube, sinon son guid « yt-<id> »."""
    m = re.search(r"(?:v=|youtu\.be/|/(?:live|shorts|embed)/)([\w-]{11})", ep.get("youtubeUrl") or "")
    video = m[1] if m else (ep["guid"][3:] if ep["guid"].startswith("yt-") else None)
    return f"https://i.ytimg.com/vi/{video}/maxresdefault.jpg" if video else None


def mise_en_scene(type_: str, tailles: list[tuple[int, int]], urls: list[str] | tuple[str, ...] = ()) -> str:
    """Mise en scène d'une page d'après son type, les proportions de ses images et leur source
    (une photo d'artiste ou un avatar est rond, une pochette carrée reste carrée)."""
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
    portrait = type_ in RONDS or any(p in url for url in urls for p in PORTRAITS)
    return "rond" if portrait else "carre"


CREDITS = (("image.tmdb.org", "affiches TMDB"), ("dzcdn.net", "pochettes Deezer"),
           ("mzstatic.com", "Apple"), ("ytimg.com", "YouTube"), ("yt3.googleusercontent.com", "YouTube"),
           ("yt3.ggpht.com", "YouTube"),
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
