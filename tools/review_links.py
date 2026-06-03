"""review_links.py — Génération d'URL « auto » par (plateforme, reco).

Miroir Python de `src/data/merchants.ts` (fonction `resolveLinks`). Utilisé
par le formulaire d'override de `review_edit.render_edit_form` pour proposer
une URL par défaut sous chaque plateforme (lien « tester » + tooltip).

Conception
----------
Le dispatch est piloté par un dict `_URL_BUILDERS: label → builder(reco, in_type)`.
Pour la plupart des labels, l'URL ne dépend pas du type courant — mais Spotify
et Deezer sont contextuels : `/shows` pour podcast, `/podcast` pour podcast
côté Deezer. La signature `auto_url(label, reco, *, in_type=None)` permet au
caller de préciser pour quel type il interroge le label, ce qui évite tout
drift TS/Py.

Sécurité
--------
`urlparse(...).hostname` est utilisé pour valider les URLs YouTube
fournies par l'utilisateur, plutôt qu'un `startswith()` naïf, afin de rejeter
les hosts trompeurs (ex. `youtube.com.evil.com`).
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Callable
from urllib.parse import urlparse

# Plateformes auto-générées par type — miroir de `linksFor*` de merchants.ts.
# Sert au formulaire d'override : pour chaque type de la reco, on propose
# un champ par plateforme pour remplacer son URL par un lien direct.
AUTO_PLATFORMS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "film":      ("JustWatch",),
    "serie":     ("JustWatch",),
    "livre":     ("Place des Libraires", "Lalibrairie.com"),
    "bd":        ("Place des Libraires", "Lalibrairie.com"),
    "musique":   ("Bandcamp", "Deezer", "Spotify", "Qobuz", "Apple Music", "YT Music", "Tidal"),
    "album":     ("Bandcamp", "Deezer", "Spotify", "Qobuz", "Apple Music", "YT Music", "Tidal"),
    "artiste":   ("Instagram", "Site officiel", "Fnac Spectacles"),
    "podcast":   ("Apple Podcasts", "Spotify", "Deezer"),
    "jeu":       ("Steam", "Itch.io"),
    "spectacle": ("Fnac Spectacles", "BilletReduc"),
    "lieu":      ("Google Maps", "Recherche"),
    "video":     ("YouTube",),
    "autre":     ("Recherche",),
}

# Hosts YouTube canoniques (validation stricte de externalIds.youtube).
_YT_HOSTS: frozenset[str] = frozenset({"www.youtube.com", "youtube.com", "youtu.be"})
_YT_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")


def _query(reco: dict) -> str:
    """Concatène title + creator pour les URLs de recherche, URL-encodé."""
    parts = [reco.get("title", ""), reco.get("creator", "") or ""]
    return urllib.parse.quote(" ".join(p for p in parts if p).strip())


def _search_url(template: str) -> Callable[[dict, str | None], str | None]:
    """Builder pour les patterns simples `.../search?q={q}` etc."""
    return lambda reco, in_type=None: template.format(q=_query(reco))


def _places_des_libraires(reco: dict, in_type: str | None = None) -> str:
    ext = reco.get("externalIds") or {}
    base = "https://www.placedeslibraires.fr/listeliv.php?base=allbooks&mots_recherche="
    isbn = ext.get("isbn")
    if isbn:
        return base + urllib.parse.quote(isbn)
    return base + _query(reco)


def _deezer(reco: dict, in_type: str | None = None) -> str:
    ext = reco.get("externalIds") or {}
    # Pour podcast : URL canonique inclut /podcast (drift TS↔Py fixé).
    if in_type == "podcast":
        return f"https://www.deezer.com/fr/search/{_query(reco)}/podcast"
    return ext.get("deezer") or f"https://www.deezer.com/fr/search/{_query(reco)}"


def _spotify(reco: dict, in_type: str | None = None) -> str:
    ext = reco.get("externalIds") or {}
    if in_type == "podcast":
        return f"https://open.spotify.com/search/{_query(reco)}/shows"
    return ext.get("spotify") or f"https://open.spotify.com/search/{_query(reco)}"


def _justwatch(reco: dict, in_type: str | None = None) -> str:
    ext = reco.get("externalIds") or {}
    return ext.get("justwatch") or f"https://www.justwatch.com/fr/recherche?q={_query(reco)}"


def _instagram(reco: dict, in_type: str | None = None) -> str:
    ext = reco.get("externalIds") or {}
    handle = (ext.get("instagram") or "").lstrip("@")
    if handle:
        return f"https://www.instagram.com/{handle}/"
    return f"https://www.google.com/search?q=site%3Ainstagram.com+{_query(reco)}"


def _site_officiel(reco: dict, in_type: str | None = None) -> str | None:
    ext = reco.get("externalIds") or {}
    return ext.get("website") or None


def _youtube(reco: dict, in_type: str | None = None) -> str:
    """Validation stricte de externalIds.youtube : id 11-char, OU URL sur host
    canonique. Tout le reste (host trompeur, schéma exotique) → recherche."""
    ext = reco.get("externalIds") or {}
    yt = ext.get("youtube") or ""
    if _YT_ID_RE.fullmatch(yt):
        return f"https://www.youtube.com/watch?v={yt}"
    if yt:
        parsed = urlparse(yt)
        if (parsed.scheme == "https"
                and parsed.hostname in _YT_HOSTS):
            return yt
    return f"https://www.youtube.com/results?search_query={_query(reco)}"


# Dispatch label → builder. Tout label absent → auto_url retourne None.
_URL_BUILDERS: dict[str, Callable[[dict, str | None], str | None]] = {
    "Place des Libraires": _places_des_libraires,
    "Lalibrairie.com":     _search_url("https://www.lalibrairie.com/livres/recherche.html?q={q}"),
    "Bandcamp":            _search_url("https://bandcamp.com/search?q={q}"),
    "Deezer":              _deezer,
    "Spotify":             _spotify,
    "Qobuz":               _search_url("https://www.qobuz.com/fr-fr/search?q={q}"),
    "Apple Music":         _search_url("https://music.apple.com/fr/search?term={q}"),
    "YT Music":            _search_url("https://music.youtube.com/search?q={q}"),
    "Tidal":               _search_url("https://tidal.com/search?q={q}"),
    "JustWatch":           _justwatch,
    "Apple Podcasts":      _search_url("https://podcasts.apple.com/fr/search?term={q}"),
    "Steam":               _search_url("https://store.steampowered.com/search/?term={q}"),
    "Itch.io":             _search_url("https://itch.io/search?q={q}"),
    "Fnac Spectacles":     _search_url("https://www.fnacspectacles.com/recherche/?searchTerm={q}"),
    "BilletReduc":         _search_url("https://www.billetreduc.com/recherche/index.htm?txt={q}"),
    "Google Maps":         _search_url("https://www.google.com/maps/search/{q}"),
    "Recherche":           _search_url("https://duckduckgo.com/?q={q}"),
    "Instagram":           _instagram,
    "Site officiel":       _site_officiel,
    "YouTube":             _youtube,
}


def auto_url(label: str, reco: dict, *, in_type: str | None = None) -> str | None:
    """URL auto-générée pour (plateforme, reco) — miroir Python de merchants.ts.

    `in_type` désambiguïse Spotify/Deezer (podcast vs musique). Si non fourni,
    on infère depuis `reco['types']` : 'podcast' prime sur le reste.

    Retourne None si le label est inconnu ou si le builder retourne None
    (ex. `Site officiel` sans `externalIds.website`).
    """
    builder = _URL_BUILDERS.get(label)
    if builder is None:
        return None
    if in_type is None:
        types = reco.get("types") or []
        if "podcast" in types:
            in_type = "podcast"
    return builder(reco, in_type)


def auto_urls_for(reco: dict) -> dict[str, str]:
    """Retourne {label: url} pour TOUS les labels miroir des types de la reco.

    Filtre les labels dont l'URL est None (ex. `Site officiel` sans website).
    Itère type par type ; pour chaque label/type, on appelle le builder avec
    `in_type=t`, ce qui résout par construction le drift Spotify/Deezer.
    """
    out: dict[str, str] = {}
    for t in reco.get("types") or []:
        for label in AUTO_PLATFORMS_BY_TYPE.get(t, ()):
            if label in out:
                continue
            url = auto_url(label, reco, in_type=t)
            if url:
                out[label] = url
    return out
