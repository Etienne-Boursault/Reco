"""Extraction et garde-fous des fiches vidéo — couche PURE.

Aucun réseau, aucun disque : ce qui lit une charge utile TMDB, en tire des
liens, et décide lesquels sont acceptables. C'est la couche où se jouent les
fausses fiches, et la seule qu'on puisse éprouver sans mock.

Extraite de `enrich_video_links.py`, qui réunissait quatre responsabilités et
dépassait 500 lignes. Les tests suivaient déjà ce découpage
(`tests/enrich_video_links/test_extractors.py`).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from apply_links import validate_link

# Les garde-fous de recherche par titre sont CALIBRÉS SUR MESURE RÉELLE dans
# `enrich_creators` (cf. `obscurity_verdict`). On les importe : en écrire
# d'autres reviendrait à recalibrer à l'aveugle.

RATE_LIMIT_SLEEP = 0.1  # 10 req/s — très en dessous des limites TMDB.

#: `RecoCard.astro` tronque l'affichage à 6 liens (`links.slice(0, 6)`).
LINKS_DISPLAY_CAP = 6

# --- Sites de fiches --------------------------------------------------------
SITE_IMDB = "imdb"
SITE_TMDB = "tmdb"
SITE_JUSTWATCH = "justwatch"
#: Ordre canonique : c'est celui dans lequel les liens sont ajoutés.
ALL_SITES = (SITE_IMDB, SITE_TMDB, SITE_JUSTWATCH)

SITE_HOSTS = {SITE_IMDB: "imdb.com", SITE_TMDB: "themoviedb.org",
              SITE_JUSTWATCH: "justwatch.com"}
#: Libellé AFFICHÉ. Celui de la page de visionnage ne nomme pas une marque
#: mais un usage : la destination a changé (JustWatch → TMDB) et pourrait
#: changer encore, tandis que « où regarder » reste vrai dans tous les cas.
#: Écrire « JustWatch » au-dessus d'un lien themoviedb.org serait un
#: mensonge visible pour le lecteur.
SITE_LABELS = {SITE_IMDB: "IMDb", SITE_TMDB: "TMDB",
               SITE_JUSTWATCH: "Où regarder"}
#: IMDb et TMDB sont des fiches (`info`) ; JustWatch agrège des offres de
#: visionnage (`streaming`), comme le fait déjà `merchants.ts`.
SITE_KINDS = {SITE_IMDB: "info", SITE_TMDB: "info", SITE_JUSTWATCH: "streaming"}

IMDB_URL = "https://www.imdb.com/title/{}/"
TMDB_URL = "https://www.themoviedb.org/{}/{}"

# --- Populations ------------------------------------------------------------
POPULATION_ID = "id-existant"
POPULATION_SEARCH = "recherche"

# --- Stratégies -------------------------------------------------------------
STRATEGY_TMDB_ID = "tmdb-id"
STRATEGY_TMDB_SEARCH = "tmdb-search"

_VIDEO_TYPES = ("film", "serie")

# --- Raisons (codes stables : servent d'agrégats dans le rapport) -----------
REASON_FILLED = "filled"
REASON_EXCLUDED = "excluded"
REASON_UNREADABLE = "unreadable-json"
REASON_NOT_VALIDATED = "not-validated"
REASON_TYPE_UNSUPPORTED = "type-not-supported"
REASON_NO_TMDB_TYPE = "no-tmdb-type"
REASON_NO_API_KEY = "no-tmdb-api-key"
REASON_HTTP_ERROR = "http-error"
REASON_TITLE_MISMATCH = "title-mismatch"
REASON_YEAR_MISMATCH = "year-mismatch"
REASON_RELEASED_AFTER_EPISODE = "released-after-episode"
REASON_NO_NEW_LINK = "no-new-link"
REASON_SEARCH_DISABLED = "search-disabled"
REASON_SEARCH_NO_MATCH = "search-no-match"
REASON_SEARCH_AMBIGUOUS = "search-ambiguous"
REASON_SEARCH_TOO_OBSCURE = "search-too-obscure"
REASON_SEARCH_ECLIPSED = "search-eclipsed"
#: Fiche TMDB SANS date de sortie. Une recherche par titre ne peut alors
#: rien prouver : `year_matches` et `release_is_plausible` renvoient tous
#: deux `True` quand la date manque, si bien que l'identité repose sur le
#: seul titre. C'est ainsi qu'un jeu télévisé canadien de 1974 (« Definition »,
#: tv/10102) a failli être posé sur une reco de série stand-up française.
REASON_SEARCH_UNDATED = "search-undated"

#: Raisons qui traduisent un DOUTE (donnée distante contradictoire) et non une
#: simple absence : ces cas méritent un œil humain.
AMBIGUOUS_REASONS = frozenset({
    REASON_TITLE_MISMATCH,
    REASON_YEAR_MISMATCH,
    REASON_RELEASED_AFTER_EPISODE,
    REASON_NO_TMDB_TYPE,
    REASON_SEARCH_AMBIGUOUS,
    REASON_SEARCH_TOO_OBSCURE,
    REASON_SEARCH_ECLIPSED,
    REASON_SEARCH_UNDATED,
})

#: Un identifiant de TITRE IMDb. `nm…` (personne) et `co…` (société) existent
#: aussi dans la base : sur `/title/` ils donnent un 404.
_RE_IMDB_TITLE_ID = re.compile(r"^tt\d{7,10}$")


# ===========================================================================
# Couche PURE — extraction & garde-fous (aucun réseau, aucun disque)
# ===========================================================================
def link_host(url: str) -> str:
    """Host normalisé d'une URL (minuscules, sans `www.`). "" si illisible."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host.removeprefix("www.")


#: Hôtes admis pour une page « où regarder ». `themoviedb.org` y figure parce
#: que TMDB sert désormais la sienne ; `justwatch.com` reste accepté pour les
#: liens déjà posés dans le corpus.
HOTES_VISIONNAGE = frozenset({"justwatch.com", "themoviedb.org"})


#: Clé unique de la page « où regarder ». Ce n'est PAS un hôte : c'est une
#: FONCTION. JustWatch et la page de visionnage de TMDB rendent le même
#: service, donc en poser une quand l'autre existe fait un doublon visible.
CLE_VISIONNAGE = "où-regarder"


def cle_couverture(url: str) -> str:
    """Ce qu'un lien COUVRE — sa FONCTION, qui n'est ni son hôte ni son chemin.

    Deux pièges opposés se referment ici, et une clé purement fondée sur
    l'hôte n'en évite qu'un :

    - la fiche TMDB et sa page de visionnage vivent sur le MÊME hôte tout en
      rendant deux services différents ; l'hôte seul rendait la seconde
      impossible à poser dès que la première existait, c'est-à-dire toujours ;
    - JustWatch et la page de visionnage TMDB vivent sur des hôtes DIFFÉRENTS
      tout en rendant le MÊME service ; distinguer par le chemin faisait alors
      apparaître deux liens « où regarder » sur la même reco.

    D'où une clé qui suit l'usage : toute page de visionnage, quel qu'en soit
    l'hôte, se réduit à `CLE_VISIONNAGE` ; le reste garde son hôte.
    """
    host = link_host(url)
    if not host:
        return ""
    if host not in HOTES_VISIONNAGE:
        return host
    chemin = url.split("?", 1)[0].rstrip("/")
    # `themoviedb.org` héberge les DEUX : seule la fiche garde son hôte.
    if host == "themoviedb.org" and not chemin.endswith("/watch"):
        return host
    return CLE_VISIONNAGE


def covered_hosts(reco: dict[str, Any]) -> set[str]:
    """Ce que la reco couvre déjà (`links` + `customLinks`).

    Sert à ne jamais poser un second lien vers une ressource déjà couverte — y
    compris quand elle a été ajoutée à la main par le serveur de relecture.
    """
    hosts: set[str] = set()
    for key in ("links", "customLinks"):
        for entry in reco.get(key) or []:
            if (cle := cle_couverture(entry.get("url") or "")):
                hosts.add(cle)
    return hosts


def imdb_id_from(payload: dict[str, Any]) -> str | None:
    """`external_ids.imdb_id` d'un payload TMDB, si c'est bien un id de TITRE."""
    block = payload.get("external_ids")
    if not isinstance(block, dict):
        return None
    raw = str(block.get("imdb_id") or "").strip()
    return raw if _RE_IMDB_TITLE_ID.match(raw) else None


def justwatch_url_from(payload: dict[str, Any]) -> str | None:
    """URL « où regarder » renvoyée par TMDB (`watch/providers` → `results.FR.link`).

    ELLE NE POINTE PLUS VERS JUSTWATCH. TMDB servait autrefois une URL
    justwatch.com ; il renvoie désormais sa PROPRE page de visionnage
    (`themoviedb.org/movie/<id>-<slug>/watch?locale=FR`). Le contrôle d'hôte
    n'avait pas suivi, et rejetait donc systématiquement ce que l'API donne :
    la passe ne posait plus un seul lien de visionnage, sans que rien ne le
    signale. Le schéma, lui, avait été renommé (`justwatch` → `watchPage`) —
    cette validation était restée en arrière.

    Les deux hôtes sont acceptés : les liens JustWatch déjà posés dans le
    corpus restent valides, et rien n'oblige TMDB à ne pas y revenir.

    Rien n'est construit : l'URL est reprise telle quelle. Seul contrôle fait
    ICI, parce qu'il est métier — un champ libre d'une API tierce n'est pas une
    garantie. La conformité du lien (https, host non vide) reste du ressort de
    `build_link`, qui applique la doctrine commune du dépôt.
    """
    block = payload.get("watch/providers")
    if not isinstance(block, dict):
        return None
    results = block.get("results")
    if not isinstance(results, dict):
        return None
    fr = results.get("FR")
    if not isinstance(fr, dict):
        return None
    url = str(fr.get("link") or "").strip()
    return url if link_host(url) in HOTES_VISIONNAGE else None


def imdb_url(imdb_id: str) -> str:
    """URL canonique d'une fiche IMDb à partir de son identifiant de titre."""
    return IMDB_URL.format(imdb_id)


def tmdb_url(kind: str, tmdb_id: str) -> str:
    """URL canonique d'une fiche TMDB (`movie` ou `tv`)."""
    return TMDB_URL.format(kind, tmdb_id)


def build_link(site: str, url: str) -> dict[str, Any] | None:
    """Lien `{label, url, kind, ethics}` validé par la doctrine du dépôt.

    Délègue à `apply_links.validate_link` : https obligatoire, enums du schéma
    Zod respectées, et forçage en `ethics: "avoid"` pour un host de la
    politique éditoriale. IMDb appartient à Amazon mais n'est pas aujourd'hui
    dans `AVOID_DOMAINS` — l'ajouter là-bas suffirait à marquer tous les liens
    posés ici, sans toucher à ce module.
    """
    link, _why = validate_link({"label": SITE_LABELS[site], "url": url,
                                "kind": SITE_KINDS[site], "ethics": "neutral"})
    return link


def candidate_links(payload: dict[str, Any], *, kind: str, tmdb_id: str,
                    sites: Sequence[str]) -> list[dict[str, Any]]:
    """Liens que le payload permet de fonder, dans l'ordre canonique.

    Un site dont l'identifiant est absent du payload ne produit aucun lien —
    c'est là que se joue le « zéro invention ».
    """
    urls: dict[str, str | None] = {
        SITE_IMDB: None,
        SITE_TMDB: tmdb_url(kind, tmdb_id),
        SITE_JUSTWATCH: justwatch_url_from(payload),
    }
    found = imdb_id_from(payload)
    if found:
        urls[SITE_IMDB] = imdb_url(found)

    out: list[dict[str, Any]] = []
    for site in ALL_SITES:
        url = urls[site]
        if site not in sites or not url:
            continue
        link = build_link(site, url)
        if link:
            out.append(link)
    return out


def missing_links(reco: dict[str, Any],
                  candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Candidats dont le host n'est pas déjà couvert par la reco."""
    hosts = covered_hosts(reco)
    return [link for link in candidates if cle_couverture(link["url"]) not in hosts]


def merge_links(reco: dict[str, Any],
                additions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Liens existants EN TÊTE, ajouts à la suite. Rien n'est retiré.

    La déduplication par host est refaite ICI, et pas seulement dans
    `missing_links` : l'idempotence de l'écriture ne doit pas dépendre du bon
    vouloir de l'appelant. Relancer la passe deux fois ne peut pas doubler un
    lien, même si la résolution est rejouée telle quelle.
    """
    out = list(reco.get("links") or [])
    hosts = covered_hosts(reco)
    for link in additions:
        cle = cle_couverture(link["url"])
        if cle in hosts:
            continue
        hosts.add(cle)
        out.append(link)
    return out


def video_type(reco: dict[str, Any]) -> str:
    """Type vidéo retenu pour le rapport (suit l'ordre déclaré dans `types`)."""
    for t in reco.get("types") or []:
        if t in _VIDEO_TYPES:
            return t
    return "?"


def parse_sites(raw: str | None) -> tuple[str, ...]:
    """`--sites` : sous-ensemble de `ALL_SITES`, remis en ordre canonique."""
    if raw is None:
        return ALL_SITES
    asked = {part.strip() for part in raw.split(",") if part.strip()}
    unknown = sorted(asked - set(ALL_SITES))
    if unknown:
        raise ValueError(f"site inconnu : {', '.join(unknown)} "
                         f"(attendu : {', '.join(ALL_SITES)})")
    return tuple(s for s in ALL_SITES if s in asked)


@dataclass(frozen=True)
class Plan:
    """Stratégie retenue pour une reco (ou raison du refus)."""

    strategy: str | None
    population: str | None = None
    reason: str = ""


def plan(reco: dict[str, Any], *, allow_search: bool = False) -> Plan:
    """Choisit la stratégie, ou explique pourquoi il n'y en a pas.

    La population est déterminée AVANT tout appel réseau : elle dit d'où
    viendra la donnée, donc quel niveau de relecture humaine elle appelle.
    """
    if not any(t in _VIDEO_TYPES for t in reco.get("types") or []):
        return Plan(None, None, REASON_TYPE_UNSUPPORTED)

    ext = reco.get("externalIds") or {}
    if ext.get("tmdb"):
        if ext.get("tmdbType") in ("movie", "tv"):
            return Plan(STRATEGY_TMDB_ID, POPULATION_ID)
        return Plan(None, POPULATION_ID, REASON_NO_TMDB_TYPE)
    if allow_search:
        return Plan(STRATEGY_TMDB_SEARCH, POPULATION_SEARCH)
    return Plan(None, POPULATION_SEARCH, REASON_SEARCH_DISABLED)


@dataclass(frozen=True)
class Resolution:
    """Résultat d'une tentative. `links` non vide ⇔ `reason == REASON_FILLED`."""

    links: tuple[dict[str, Any], ...]
    reason: str
    source: str | None
    population: str | None = None
    detail: str = ""
