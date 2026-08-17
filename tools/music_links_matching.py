"""Appariement et garde-fous des liens musicaux — couche PURE.

Aucun réseau, aucun disque : tout ce qui décide SI un candidat distant
correspond à une reco, et POURQUOI il est refusé le cas échéant. C'est la
couche où se jouent les faux appariements, et la seule qu'on puisse éprouver
sans mock.

Extraite de `enrich_music_links.py`, qui dépassait 500 lignes en réunissant
quatre couches. Les tests suivaient déjà ce découpage
(`tests/enrich_music_links/test_matching.py`).
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

from common import normalize_text

# --- Constantes réseau ------------------------------------------------------
DEEZER_BASE = "https://api.deezer.com"
ITUNES_BASE = "https://itunes.apple.com"
HTTP_TIMEOUT = 15
RATE_LIMIT_SLEEP = 0.1
SEARCH_LIMIT = 10

#: L'API iTunes plafonne à une vingtaine d'appels par minute et répond HTTP
#: 429 au-delà. Sans réessai, ce 429 se déguiserait en `no-match` — un refus
#: pour cause d'infrastructure, indiscernable d'un refus de fond dans le
#: rapport. On patiente et on retente une fois.
RETRY_AFTER_SLEEP = 5.0
HTTP_TOO_MANY_REQUESTS = 429

# --- Garde-fous -------------------------------------------------------------
#: Seuil de similarité pour l'appariement d'un NOM D'ARTISTE. Les titres de
#: recos viennent de transcriptions automatiques et charrient des fautes
#: régulières (« Yann Tierssen » pour Tiersen, « Corey Wong » pour Cory Wong,
#: « Sophia Bellabès » pour Belabbès). Un seuil haut absorbe la faute de frappe
#: SANS ouvrir la porte aux homonymes : un homonyme se distingue par une
#: égalité EXACTE du nom, pas par une quasi-égalité.
ARTIST_MATCH_THRESHOLD = 0.88

# --- Plateformes ------------------------------------------------------------
PLATFORM_DEEZER = "deezer"
PLATFORM_APPLE = "apple"

#: Hôte canonique et libellé affiché de chaque plateforme. `host` sert à
#: reconnaître un lien DÉJÀ posé (par un humain ou une passe précédente).
PLATFORMS: dict[str, dict[str, str]] = {
    PLATFORM_DEEZER: {"host": "deezer.com", "label": "Deezer"},
    PLATFORM_APPLE: {"host": "music.apple.com", "label": "Apple Music"},
}

#: Plateformes d'écoute reconnues au-delà de celles que l'outil sait remplir :
#: une reco déjà pourvue sur Qobuz n'est pas « sans plateforme ».
KNOWN_LISTENING_HOSTS = frozenset({
    "deezer.com", "music.apple.com", "open.spotify.com", "qobuz.com",
})

LINK_KIND = "streaming"
LINK_ETHICS = "neutral"

# --- Stratégies -------------------------------------------------------------
STRATEGY_PROMOTE_DEEZER_ID = "promote-deezer-id"
STRATEGY_SEARCH_ALBUM = "search-album"
STRATEGY_SEARCH_TRACK = "search-track"
STRATEGY_SEARCH_ARTIST = "search-artist"

#: Stratégie de recherche correspondant à chaque type de contenu visé.
_SEARCH_STRATEGY = {
    "album": STRATEGY_SEARCH_ALBUM,
    "track": STRATEGY_SEARCH_TRACK,
    "artist": STRATEGY_SEARCH_ARTIST,
}

TYPE_MUSIQUE = "musique"
TYPE_ALBUM = "album"
TYPE_ARTISTE = "artiste"
#: Types explicitement musicaux — les seuls sur lesquels l'outil travaille
#: sans opt-in (cf. « POURQUOI `artiste` EST OPT-IN »).
STRONG_MUSIC_TYPES = (TYPE_ALBUM, TYPE_MUSIQUE)
SUPPORTED_TYPES = (TYPE_ALBUM, TYPE_MUSIQUE, TYPE_ARTISTE)

# --- Raisons (codes stables : agrégats du rapport) --------------------------
REASON_LINKED = "linked"
REASON_ALREADY_COMPLETE = "already-complete"
REASON_EXCLUDED = "excluded"
REASON_UNREADABLE = "unreadable-json"
REASON_NOT_VALIDATED = "not-validated"
REASON_TYPE_UNSUPPORTED = "type-not-musical"
REASON_ARTIST_TYPE_UNPROVEN = "artist-type-unproven"
REASON_NO_CREATOR = "no-creator-to-verify"
REASON_HTTP_ERROR = "http-error"
REASON_NO_MATCH = "no-match"
REASON_AMBIGUOUS = "ambiguous"
REASON_TITLE_MISMATCH = "title-mismatch"
REASON_ARTIST_MISMATCH = "artist-mismatch"
REASON_BAD_DEEZER_URL = "deezer-unparsable-url"
REASON_STORED_KIND_MISMATCH = "stored-kind-mismatch"

#: Raisons qui traduisent un DOUTE (donnée distante contradictoire) plutôt
#: qu'une absence de donnée : ces cas méritent un œil humain.
AMBIGUOUS_REASONS = frozenset({
    REASON_AMBIGUOUS,
    REASON_TITLE_MISMATCH,
    REASON_ARTIST_MISMATCH,
    REASON_BAD_DEEZER_URL,
    REASON_STORED_KIND_MISMATCH,
})

_RE_DEEZER_URL = re.compile(
    r"deezer\.com/(?:[a-z]{2}/)?(track|album|artist)/(\d+)", re.IGNORECASE
)


# ===========================================================================
# Couche PURE — appariement & garde-fous (aucun réseau, aucun disque)
# ===========================================================================
def names_match(a: str | None, b: str | None,
                *, threshold: float = ARTIST_MATCH_THRESHOLD) -> bool:
    """True si deux noms d'artiste désignent vraisemblablement la même personne.

    Égalité après normalisation, sinon similarité de séquence ≥ `threshold`
    (cf. `ARTIST_MATCH_THRESHOLD` pour le pourquoi du seuil).
    """
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def creator_names(creator: str | None) -> list[str]:
    """Décompose un `creator` en noms individuels.

    Un `creator` peut porter plusieurs noms (« Damon Albarn, Jamie Hewlett »
    pour Gorillaz) : l'API n'en renverra qu'un, et il suffit qu'il corresponde
    à l'un d'eux.
    """
    return [part.strip() for part in (creator or "").split(",") if part.strip()]


def artist_matches_creator(remote_artist: str | None,
                           creator: str | None) -> bool:
    """True si l'artiste renvoyé par l'API correspond au `creator` de la reco."""
    return any(names_match(remote_artist, name) for name in creator_names(creator))


def titles_match_strict(a: str | None, b: str | None) -> bool:
    """Égalité de titres APRÈS normalisation seulement — rien d'autre.

    Aucune inclusion de mots, aucune similarité : en recherche libre il n'y a
    pas d'identifiant pour ancrer le résultat, et la moindre permissivité fait
    entrer « Amélie » pour « Amélie Poulain ». La normalisation absorbe déjà
    casse, accents et ponctuation.
    """
    na, nb = normalize_text(a), normalize_text(b)
    return bool(na) and na == nb


def link_host(url: str) -> str:
    """Hôte d'une URL, sans `www.` ni casse. Vide si l'URL est illisible.

    `urlparse(...).hostname` lève `ValueError` sur un IPv6 malformé
    (« https://[::1 ») : un lien saisi à la main ne doit pas faire tomber la
    passe entière.
    """
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def existing_hosts(reco: dict[str, Any]) -> set[str]:
    """Hôtes des liens DÉJÀ posés sur la reco."""
    return {h for link in (reco.get("links") or [])
            for h in [link_host(str(link.get("url") or ""))] if h}


def missing_platforms(reco: dict[str, Any]) -> list[str]:
    """Plateformes que l'outil sait remplir et qui manquent à cette reco.

    Un lien existant n'est jamais écrasé : la plateforme est simplement retirée
    de la liste des cibles.
    """
    hosts = existing_hosts(reco)
    return [p for p, meta in PLATFORMS.items() if meta["host"] not in hosts]


def has_any_listening_link(reco: dict[str, Any]) -> bool:
    """True si la reco porte déjà au moins un lien d'écoute reconnu."""
    return bool(existing_hosts(reco) & KNOWN_LISTENING_HOSTS)


def primary_type(reco: dict[str, Any]) -> str:
    """Type retenu pour l'agrégation du rapport (le 1er type musical, sinon le 1er)."""
    types = reco.get("types") or []
    for t in SUPPORTED_TYPES:
        if t in types:
            return t
    return types[0] if types else "?"


def parse_deezer_url(url: str | None) -> tuple[str, str] | None:
    """Extrait (kind, id) d'une URL Deezer. None si la forme est inattendue."""
    m = _RE_DEEZER_URL.search(url or "")
    return (m.group(1).lower(), m.group(2)) if m else None


def content_kind(reco: dict[str, Any]) -> str:
    """Type de contenu visé par la recherche, d'après les types de la reco.

    L'album prime sur le morceau, qui prime sur la page artiste : une reco
    typée `album,musique` désigne l'album.
    """
    types = reco.get("types") or []
    if TYPE_ALBUM in types:
        return "album"
    if TYPE_MUSIQUE in types:
        return "track"
    return "artist"


@dataclass(frozen=True)
class Plan:
    """Stratégie retenue pour une reco (ou raison du refus)."""

    strategy: str | None
    kind: str = ""
    reason: str = ""


def plan(reco: dict[str, Any], *, allow_artists: bool = False) -> Plan:
    """Choisit la stratégie, ou explique pourquoi il n'y en a pas.

    L'opt-in `artiste` est évalué AVANT tout le reste : un identifiant Deezer
    déjà stocké ne vaut pas preuve du caractère musical de la reco. Ces
    identifiants viennent de l'ancien `enrich_music.py`, qui retenait le
    premier résultat sans rien vérifier — c'est précisément ainsi qu'un
    humoriste se retrouve avec la page d'un musicien homonyme.
    """
    types = reco.get("types") or []

    if not any(t in SUPPORTED_TYPES for t in types):
        return Plan(None, reason=REASON_TYPE_UNSUPPORTED)
    if not any(t in STRONG_MUSIC_TYPES for t in types) and not allow_artists:
        return Plan(None, reason=REASON_ARTIST_TYPE_UNPROVEN)

    kind = content_kind(reco)
    ext = reco.get("externalIds") or {}
    deezer_host = PLATFORMS[PLATFORM_DEEZER]["host"]
    if ext.get("deezer") and deezer_host not in existing_hosts(reco):
        return Plan(STRATEGY_PROMOTE_DEEZER_ID, kind)
    return Plan(_SEARCH_STRATEGY[kind], kind)


@dataclass(frozen=True)
class Candidate:
    """Un résultat d'API normalisé, indépendant de la plateforme.

    `title` est vide pour un candidat de type `artist` : c'est `artist` qui
    porte alors le nom recherché.
    """

    platform: str
    kind: str
    url: str
    artist: str
    title: str = ""
    ident: str = ""


@dataclass(frozen=True)
class MusicLink:
    """Un lien prêt à écrire dans `links`, avec sa provenance."""

    platform: str
    label: str
    url: str
    source: str

    def as_link(self) -> dict[str, str]:
        """Forme stockée dans le JSON de la reco (schéma Zod `link`)."""
        return {"label": self.label, "url": self.url,
                "kind": LINK_KIND, "ethics": LINK_ETHICS}


@dataclass(frozen=True)
class Resolution:
    """Résultat d'une tentative sur UNE plateforme."""

    link: MusicLink | None
    reason: str
    detail: str = ""


def verdict(reco: dict[str, Any], candidates: Sequence[Candidate],
            *, want_artist_page: bool,
            anchored: bool = False) -> tuple[Candidate | None, str, str]:
    """Applique les garde-fous à une liste de candidats.

    Renvoie `(candidat retenu, raison, détail)`. Un seul candidat peut être
    retenu : dès que deux identités distinctes survivent, on refuse plutôt que
    de trancher (`ambiguous`).

    Pour une page ARTISTE, seul le nom compte — il n'y a pas de titre d'œuvre
    à comparer. Pour un morceau ou un album, le titre ET l'artiste doivent
    correspondre : c'est la double condition qui protège des homonymes.

    `anchored` distingue les candidats issus d'un IDENTIFIANT déjà stocké de
    ceux d'une recherche libre. Le diagnostic diffère : qu'une recherche ne
    ramène aucun titre correspondant est banal (`no-match`), mais qu'une fiche
    désignée par un identifiant porte un autre titre signifie que
    l'identifiant lui-même est faux (`title-mismatch`) — une information qui
    mérite un œil humain.
    """
    creator = reco.get("creator")
    title = reco.get("title")

    kept: list[Candidate] = []
    artist_mismatch = False
    for cand in candidates:
        if want_artist_page:
            if names_match(cand.artist, title) or artist_matches_creator(
                    cand.artist, creator):
                kept.append(cand)
            continue
        if not titles_match_strict(title, cand.title):
            continue
        # Le titre correspond mais pas l'artiste : c'est l'homonymie type
        # (« Amélie »), le cas que ce garde-fou existe pour arrêter.
        if not artist_matches_creator(cand.artist, creator):
            artist_mismatch = True
            continue
        kept.append(cand)

    if not kept:
        if artist_mismatch:
            return None, REASON_ARTIST_MISMATCH, _first_detail(candidates)
        if anchored:
            return None, REASON_TITLE_MISMATCH, _first_detail(candidates)
        return None, REASON_NO_MATCH, _first_detail(candidates)

    identities = {c.ident or c.url for c in kept}
    if len(identities) > 1:
        return None, REASON_AMBIGUOUS, (
            f"{len(identities)} candidats distincts : "
            + " · ".join(f"{c.artist} — {c.title or 'page artiste'}" for c in kept[:3])
        )
    return kept[0], REASON_LINKED, ""


def _first_detail(candidates: Sequence[Candidate]) -> str:
    """Décrit le premier candidat écarté, pour le rapport."""
    if not candidates:
        return ""
    c = candidates[0]
    return f"l'API répond « {c.artist} — {c.title or 'page artiste'} »"


@dataclass(frozen=True)
class RecoOutcome:
    """Sort complet d'une reco : les liens trouvés et les refus, par plateforme."""

    links: tuple[MusicLink, ...]
    refusals: tuple[tuple[str, str, str], ...]  # (plateforme, raison, détail)
    reason: str
