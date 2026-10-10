"""Décide QUELS liens de plateformes vidéo une reco film/série peut recevoir.

Aucun réseau, aucun disque : les garde-fous sont ici, éprouvables sans appeler
Wikidata ni ARTE. Le réseau et la boucle vivent dans `streaming_links` (même
découpage que `wikidata_matching` / `wikidata_links`).

POURQUOI CETTE PASSE
--------------------
`fiches_tmdb` n'écrit que la page agrégatrice « Où regarder » : le lien DIRECT
vers Netflix, Prime Video, Disney+, Apple TV ou ARTE était toujours posé à la
main (Acharnés, Fleabag, Samuel, Les Groos sur S6-E04).

DEUX PREUVES, JAMAIS UNE SEULE
------------------------------
1. **L'identité** : Wikidata est interrogé par l'identifiant TMDB que la reco
   porte déjà (P4947 film, P4983 série) — un fait, pas une ressemblance de
   titre. L'entité donne alors l'identifiant de chaque plateforme.
2. **La disponibilité en France** : un identifiant Netflix existe pour une
   œuvre que Netflix ne diffuse pas chez nous. On n'écrit donc une plateforme
   que si TMDB la liste parmi les fournisseurs FR (`watchProviders`, posés par
   `fiches_tmdb` sans clé à relire). Mesuré le 2026-10-10 sur les 217 recos du
   corpus identifiées par Wikidata : 47 portent un identifiant Netflix sans
   lien Netflix, et TMDB n'en liste que 3 comme disponibles en France.

ARTE.tv n'a pas d'identifiant Wikidata exploitable : sa page de recherche est
rendue côté serveur, on y lit le lien candidat, puis la page elle-même doit
corroborer (cf. `page_arte_corrobore`).

PROPRIÉTÉS ET FORMATS, VÉRIFIÉS LE 2026-10-10
----------------------------------------------
Par l'API Wikidata (formateur P1630) et en ouvrant les pages, et calibrés sur
le corpus : P1874 Netflix rend le lien posé à la main dans 44 cas sur 45, P9751
/ P9586 Apple TV dans 29 sur 30, P1265 / P1267 AlloCiné dans 98 sur 102.
- P8055 « Amazon Prime Video ID » est un ASIN de la boutique AMÉRICAINE : la
  page `primevideo.com/-/fr/detail/<ASIN>` répond 404 (Fleabag, B0875MH9J8).
  Elle n'est donc PAS lue ; seuls P14440 (identifiant Prime Video) et P14462
  (GTI `amzn1.dv.gti.…`) le sont, et leur page FR répond 200.
- P13902 « Disney+ browse ID » vaut `entity-…` pour une œuvre, mais `page-…`
  pour une collection (« Films et séries Les Simpson ») : seul `entity-` est
  retenu. Les anciens P7595 / P7596 redirigent vers la page `entity-` : le
  réseau la résout (cf. `streaming_links`).
- Apple TV exige un segment de titre dans l'URL du corpus
  (`/fr/show/fleabag/umc.cmc.…`) : la page sans segment redirige vers la forme
  canonique, que le réseau lit plutôt que de fabriquer le segment.
"""
from __future__ import annotations

import html
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from common import normalize_text, slugify
from wikidata_matching import (
    RAISON_AMBIGUOUS,
    RAISON_ID_MISMATCH,
    RAISON_NO_ENTITY,
    RAISON_NO_NEW_LINK,
    RAISON_OK,
    Entite,
    Lien,
    hote,
)

TYPES_SERVIS = ("film", "serie")
PROP_TMDB = {"movie": "P4947", "tv": "P4983"}
PROP_IMDB = "P345"

RAISON_NO_TMDB = "no-tmdb-id"
RAISON_PAS_EN_FRANCE = "not-offered-in-france"
RAISON_ARTE_INTROUVABLE = "arte-not-found"
RAISON_ARTE_NON_CORROBORE = "arte-unproven"

#: Valeur qu'un résolveur réseau doit remplacer par l'URL que le site déclare.
A_RESOUDRE = "a-resoudre:"


@dataclass(frozen=True)
class Plateforme:
    """Une plateforme : son étiquetage au corpus, et comment TMDB la nomme.

    `abonnement` et `achat` sont des noms de fournisseurs TMDB : le premier
    donne un lien `streaming`, le second un lien `buy` (« Apple TV Store »
    vend, il ne diffuse pas — 22 liens Apple TV du corpus sont en `buy`).
    """

    nom: str
    label: str
    ethics: str
    abonnement: tuple[str, ...]
    achat: tuple[str, ...] = ()


#: Ordre d'affichage : l'indépendant d'abord, Amazon en dernier (arbitrage
#: éditorial du 2026-07-19 — marqué `avoid`, jamais retiré). C'est aussi l'ordre
#: que l'éditeur a choisi à la main pour Fleabag (Apple TV puis Prime Video).
ARTE = Plateforme("arte", "ARTE.tv", "indie", ("Arte",))
NETFLIX = Plateforme("netflix", "Netflix", "neutral",
                     ("Netflix", "Netflix Standard with Ads", "Netflix basic with Ads"))
DISNEY = Plateforme("disney", "Disney+", "neutral", ("Disney Plus",))
APPLE = Plateforme("apple", "Apple TV", "neutral",
                   ("Apple TV", "Apple TV Plus", "Apple TV+"), ("Apple TV Store",))
PRIME = Plateforme("prime", "Prime Video", "avoid",
                   ("Amazon Prime Video", "Amazon Prime Video with Ads"), ("Amazon Video",))
PLATEFORMES: tuple[Plateforme, ...] = (ARTE, NETFLIX, DISNEY, APPLE, PRIME)
SOURCES_PLATEFORMES = frozenset(p.nom for p in PLATEFORMES)

ALLOCINE = Lien("allocine", "info", "neutral", "AlloCiné", "")
LABEL_OU_REGARDER = "Où regarder"

_RE_NETFLIX = re.compile(r"^\d{6,9}$")
_RE_PRIME = re.compile(r"^(?:[0-9A-Z]{26}|amzn1\.dv\.gti\.[0-9a-f-]{36})$")
_RE_DISNEY_ENTITE = re.compile(r"^entity-[0-9a-f-]{36}$")
_RE_DISNEY_ANCIEN = re.compile(r"^[0-9A-Za-z]{12}$")
_RE_APPLE = re.compile(r"^umc\.cmc\.[a-z0-9]+$")
_RE_IMDB_RECO = re.compile(r"imdb\.com/title/(tt\d+)")


def type_tmdb(reco: dict[str, Any]) -> tuple[str, str, str] | None:
    """(propriété Wikidata, identifiant TMDB, `movie`|`tv`), ou None."""
    ext = reco.get("externalIds") or {}
    tmdb, genre = str(ext.get("tmdb") or ""), ext.get("tmdbType")
    if not tmdb.isdigit() or genre not in PROP_TMDB:
        return None
    return PROP_TMDB[genre], tmdb, genre


def servie(reco: dict[str, Any]) -> bool:
    return bool(set(reco.get("types") or []) & set(TYPES_SERVIS))


def genre_offert(plateforme: Plateforme, reco: dict[str, Any]) -> str | None:
    """`streaming`, `buy`, ou None si TMDB ne la liste pas en France.

    Les « chaînes » (« Apple TV Amazon Channel ») ne comptent pas : l'œuvre y
    est diffusée par un tiers, pas par la plateforme elle-même.
    """
    noms = {str(p.get("label") or "") for p in reco.get("watchProviders") or []}
    if noms & set(plateforme.abonnement):
        return "streaming"
    if noms & set(plateforme.achat):
        return "buy"
    return None


def _lien(plateforme: Plateforme, genre: str, url: str) -> Lien:
    return Lien(plateforme.nom, genre, plateforme.ethics, plateforme.label, url)


def url_plateforme(plateforme: Plateforme, entite: Entite, genre_tmdb: str) -> str | None:
    """URL de la plateforme d'après l'entité, ou à résoudre, ou None."""
    if plateforme is NETFLIX:
        valeur = entite.valeur("P1874") or ""
        return f"https://www.netflix.com/title/{valeur}" if _RE_NETFLIX.match(valeur) else None
    if plateforme is PRIME:
        for prop in ("P14440", "P14462"):
            valeur = entite.valeur(prop) or ""
            if _RE_PRIME.match(valeur):
                return A_RESOUDRE + f"https://www.primevideo.com/-/fr/detail/{valeur}"
        return None
    if plateforme is DISNEY:
        valeur = entite.valeur("P13902") or ""
        if _RE_DISNEY_ENTITE.match(valeur):
            return f"https://www.disneyplus.com/fr-fr/browse/{valeur}"
        prop, chemin = ("P7596", "series/wp") if genre_tmdb == "tv" else ("P7595", "movies/wd")
        valeur = entite.valeur(prop) or ""
        if _RE_DISNEY_ANCIEN.match(valeur):
            return A_RESOUDRE + f"https://www.disneyplus.com/{chemin}/{valeur}"
        return None
    if plateforme is APPLE:
        prop, chemin = ("P9751", "show") if genre_tmdb == "tv" else ("P9586", "movie")
        valeur = entite.valeur(prop) or ""
        return (A_RESOUDRE + f"https://tv.apple.com/fr/{chemin}/{valeur}"
                if _RE_APPLE.match(valeur) else None)
    return None


def url_allocine(entite: Entite, genre_tmdb: str) -> str | None:
    if genre_tmdb == "tv":
        valeur = entite.valeur("P1267") or ""
        gabarit = "https://www.allocine.fr/series/ficheserie_gen_cserie={}.html"
    else:
        valeur = entite.valeur("P1265") or ""
        gabarit = "https://www.allocine.fr/film/fichefilm_gen_cfilm={}.html"
    return gabarit.format(valeur) if valeur.isdigit() else None


def imdb_de_la_reco(reco: dict[str, Any]) -> str | None:
    for lien in reco.get("links") or []:
        if m := _RE_IMDB_RECO.search(str(lien.get("url") or "")):
            return m.group(1)
    return None


def hotes_presents(reco: dict[str, Any]) -> set[str]:
    return {hote(str(e.get("url") or "")) for e in reco.get("links") or []}


@dataclass(frozen=True)
class VerdictWikidata:
    """Liens proposés par l'entité (certains `A_RESOUDRE`), ou pourquoi aucun."""

    liens: tuple[Lien, ...]
    raison: str
    qid: str | None = None
    detail: str = ""


def verdict_wikidata(reco: dict[str, Any], entites: Sequence[Entite]) -> VerdictWikidata:
    """Une seule entité, cohérente avec la reco, puis ses plateformes offertes en France."""
    cle = type_tmdb(reco)
    if cle is None:
        return VerdictWikidata((), RAISON_NO_TMDB)
    prop, tmdb, genre_tmdb = cle
    uniques = {e.qid: e for e in entites}
    if not uniques:
        return VerdictWikidata((), RAISON_NO_ENTITY)
    if len(uniques) > 1:
        return VerdictWikidata((), RAISON_AMBIGUOUS, detail=" ".join(sorted(uniques)))
    entite = next(iter(uniques.values()))
    if tmdb not in (entite.claims.get(prop) or ()):
        return VerdictWikidata((), RAISON_ID_MISMATCH, entite.qid, detail=f"{prop}≠{tmdb}")
    imdb = imdb_de_la_reco(reco)
    connus = entite.claims.get(PROP_IMDB) or ()
    if imdb and connus and imdb not in connus:
        return VerdictWikidata((), RAISON_ID_MISMATCH, entite.qid,
                               detail=f"{PROP_IMDB} reco={imdb} wikidata={connus[0]}")

    deja = hotes_presents(reco)
    liens: list[Lien] = []
    absentes: list[str] = []
    for plateforme in PLATEFORMES:
        url = url_plateforme(plateforme, entite, genre_tmdb)
        if url is None:
            continue
        genre = genre_offert(plateforme, reco)
        if genre is None:
            absentes.append(plateforme.label)
        elif hote(url.removeprefix(A_RESOUDRE)) not in deja:
            liens.append(_lien(plateforme, genre, url))
    url = url_allocine(entite, genre_tmdb)
    if url and hote(url) not in deja:
        liens.append(Lien(ALLOCINE.source, ALLOCINE.kind, ALLOCINE.ethics, ALLOCINE.label, url))
    detail = f"hors de France : {', '.join(absentes)}" if absentes else ""
    raison = RAISON_OK if liens else (RAISON_PAS_EN_FRANCE if absentes else RAISON_NO_NEW_LINK)
    return VerdictWikidata(tuple(liens), raison, entite.qid, detail)


# ===== ARTE =================================================================
_RE_ARTE_SERIE = re.compile(r'href="(?:https://www\.arte\.tv)?/fr/videos/(RC-\d+)/([a-z0-9-]+)/"')
_RE_ARTE_FILM = re.compile(
    r'href="(?:https://www\.arte\.tv)?/fr/videos/(\d{6}-\d{3}-[A-Z])/([a-z0-9-]+)/"')
_RE_TITRE_PAGE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_RE_SEPARATEURS_CREATEUR = re.compile(r"\s*(?:,|&|/|\bet\b)\s*")


def titres_candidats(reco: dict[str, Any]) -> list[str]:
    """Le titre, puis sans sa parenthèse : « Acharnés (Beef) » → « Acharnés »."""
    titre = str(reco.get("title") or "").strip()
    court = re.sub(r"\s*\([^)]*\)\s*$", "", titre).strip()
    return [t for t in dict.fromkeys((titre, court)) if t]


def liens_arte_de_recherche(page: str, titre: str, genre_tmdb: str) -> list[str]:
    """Chemins `/fr/videos/…/` de la recherche dont le segment de titre est EXACT.

    Une série se publie sous une collection `RC-…`, un film sous un programme
    `123456-000-A`. Toute page de recherche porte aussi deux séries mises en
    avant (« Catastrophe », « Taxe-moi si tu peux » le 2026-10-10) : l'égalité
    du segment de titre les écarte.
    """
    motif = _RE_ARTE_SERIE if genre_tmdb == "tv" else _RE_ARTE_FILM
    voulu = slugify(titre)
    chemins = [f"https://www.arte.tv/fr/videos/{ident}/{segment}/"
               for ident, segment in motif.findall(page) if segment == voulu]
    return list(dict.fromkeys(chemins))


def noms_du_createur(reco: dict[str, Any]) -> list[str]:
    createur = str(reco.get("creator") or "")
    return [n for n in _RE_SEPARATEURS_CREATEUR.split(createur) if normalize_text(n)]


def page_arte_corrobore(page: str, reco: dict[str, Any], titre: str) -> tuple[bool, str]:
    """La page ouverte est-elle bien l'œuvre ? (verdict, raison du refus).

    Le titre de la page doit commencer par le titre exact (« Samuel - Séries et
    fictions | ARTE »). Puis une preuve de plus, car un titre seul ne prouve
    rien : le créateur nommé par la reco doit figurer dans la page (« Une série
    créée et réalisée par David Mirailles ») ; à défaut de créateur, TMDB doit
    lister ARTE en France, ou la personne doit avoir dit « Arte » en
    recommandant (Les Groos : « la mini-série Arte »).
    """
    m = _RE_TITRE_PAGE.search(page)
    entete = html.unescape(m.group(1)).strip() if m else ""
    if "ARTE" not in entete or normalize_text(entete.split(" - ")[0]) != normalize_text(titre):
        return False, f"titre de page : {entete[:60]!r}"
    noms = noms_du_createur(reco)
    if noms:
        texte = normalize_text(html.unescape(page))
        if any(f" {normalize_text(n)} " in f" {texte} " for n in noms):
            return True, ""
        return False, "créateur absent de la page"
    if genre_offert(ARTE, reco):
        return True, ""
    if re.search(r"\barte\b", normalize_text(reco.get("quote"))):
        return True, ""
    return False, "ni créateur, ni fournisseur ARTE, ni mention d'Arte"


def lien_arte(url: str) -> Lien:
    return _lien(ARTE, "streaming", url)


# ===== placement ============================================================
def placer(existants: list[dict[str, Any]], lien: Lien) -> int:
    """Plateformes EN TÊTE (la carte n'affiche que six liens), dans l'ordre de
    `PLATEFORMES` ; AlloCiné juste avant « Où regarder », comme l'éditeur l'a
    posé pour Fleabag ; à défaut, à la fin."""
    if lien.source in SOURCES_PLATEFORMES:
        rang = [p.nom for p in PLATEFORMES].index(lien.source)
        position = 0
        for i, existant in enumerate(existants):
            source = _source_de(existant)
            if source is None or [p.nom for p in PLATEFORMES].index(source) > rang:
                break
            position = i + 1
        return position
    for i, existant in enumerate(existants):
        if existant.get("label") == LABEL_OU_REGARDER:
            return i
    return len(existants)


def _source_de(lien: dict[str, Any]) -> str | None:
    """Plateforme d'un lien existant, reconnue à son hôte."""
    hotes = {"arte.tv": "arte", "netflix.com": "netflix", "disneyplus.com": "disney",
             "tv.apple.com": "apple", "primevideo.com": "prime"}
    return hotes.get(hote(str(lien.get("url") or "")))
