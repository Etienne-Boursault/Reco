"""Décide SI une entité Wikidata est bien la personne recommandée — aucun réseau.

Séparé de `wikidata_links` (qui interroge et écrit) parce que c'est ici que sont
les garde-fous, et qu'ils doivent être éprouvables sans appeler Wikidata. Les
codes de raison doivent rester STABLES : ce sont eux qui permettent de comparer
deux passes.

La doctrine et les mesures qui justifient ces seuils sont dans l'en-tête de
`enrich_wikidata_links`.
"""
from __future__ import annotations

import re
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from common import normalize_text

TYPE_ARTISTE = "artiste"
#: Seul type servi. Mesuré le 2026-09-27 : les entités de type `lieu` et `autre`
#: du corpus (une exposition, deux associations) sont absentes de Wikidata, donc
#: toute liste de natures admises pour elles serait de la devinette non testable.
TYPES_SERVIS: tuple[str, ...] = (TYPE_ARTISTE,)

#: Natures (P31) acceptées par type, libellés relevés sur Wikidata le 2026-09-27 :
#: Q5 « être humain », Q215380 « groupe de musique », Q9212979 « duo musical »
#: (Bigflo & Oli ne porte QUE ce dernier : un duo n'est pas toujours un groupe).
#: Ce qui est refusé compte autant : Q486972 « établissement humain » est la
#: nature du village camerounais nommé « Yoa », homonyme de la chanteuse.
NATURES_ADMISES: dict[str, frozenset[str]] = {
    TYPE_ARTISTE: frozenset({"Q5", "Q215380", "Q9212979"}),
}

PROP_DEEZER = "P2722"
PROP_SPOTIFY = "P1902"
#: Identifiants qu'une reco peut déjà porter, et qui valent preuve d'identité.
PROPS_PREUVE = (PROP_DEEZER, PROP_SPOTIFY)

RAISON_OK = "ok"
RAISON_NO_ENTITY = "no-entity"
RAISON_AMBIGUOUS = "ambiguous"
RAISON_TYPE_INCOMPATIBLE = "type-incompatible"
RAISON_LABEL_MISMATCH = "label-mismatch"
RAISON_ID_MISMATCH = "id-mismatch"
RAISON_NO_NEW_LINK = "no-new-link"
RAISON_TYPE_UNSUPPORTED = "type-unsupported"
RAISON_NOT_VALIDATED = "not-validated"
RAISON_HTTP_ERROR = "http-error"
RAISON_UNREADABLE = "unreadable"
#: Refus qui méritent un œil humain, par opposition à « rien à trouver ».
RAISONS_A_ARBITRER = frozenset({RAISON_AMBIGUOUS, RAISON_ID_MISMATCH,
                                RAISON_TYPE_INCOMPATIBLE, RAISON_LABEL_MISMATCH})

PREUVE_IDENTIFIANT = "identifiant"
PREUVE_TITRE = "titre+nature"

_RE_DEEZER_ARTISTE = re.compile(r"deezer\.com/(?:[a-z]{2}/)?artist/(\d+)")
_RE_SPOTIFY_ARTISTE = re.compile(
    r"open\.spotify\.com/(?:intl-[a-z-]+/)?artist/([A-Za-z0-9]+)")


@dataclass(frozen=True)
class Source:
    """Une source de lien : son nom interne, et comment le corpus l'étiquette."""

    nom: str
    kind: str
    ethics: str
    label: str


#: Étiquetage relevé dans le corpus le 2026-09-27, majorité par hôte : Wikipédia
#: info/indie (33 contre 17), Instagram social/neutral (285), AlloCiné (164) et
#: IMDb (358) info/neutral, site officiel official/indie (336) libellé
#: « Site officiel » (73).
SOURCE_SITE = Source("site-officiel", "official", "indie", "Site officiel")
SOURCE_INSTAGRAM = Source("instagram", "social", "neutral", "Instagram")
SOURCE_ALLOCINE = Source("allocine", "info", "neutral", "AlloCiné")
SOURCE_IMDB = Source("imdb", "info", "neutral", "IMDb")
SOURCE_WIKIPEDIA = Source("wikipedia", "info", "indie", "Wikipédia")


def _url_site(valeur: str) -> str | None:
    """P856 porte déjà une URL : on la prend telle quelle, ou pas du tout."""
    return valeur if valeur.startswith(("http://", "https://")) else None


def _url_instagram(valeur: str) -> str | None:
    return f"https://www.instagram.com/{valeur}/" if valeur else None


def _url_allocine(valeur: str) -> str | None:
    return (f"https://www.allocine.fr/personne/fichepersonne_gen_cpersonne={valeur}.html"
            if valeur.isdigit() else None)


def _url_imdb(valeur: str) -> str | None:
    """`nm…` = personne, `tt…` = œuvre. Tout autre préfixe : on ne devine pas."""
    if valeur.startswith("nm"):
        return f"https://www.imdb.com/name/{valeur}/"
    if valeur.startswith("tt"):
        return f"https://www.imdb.com/title/{valeur}/"
    return None


#: Caractères que le corpus laisse LITTÉRAUX dans une URL Wikipédia.
#: Relevé sur ses 6 titres parenthésés : « Iliona_(chanteuse) »,
#: « Le_Monde_%C3%A0_l'Envers_(cha%C3%AEne_YouTube) »,
#: « Mr._et_Mrs._Smith_(s%C3%A9rie_t%C3%A9l%C3%A9vis%C3%A9e,_2024) » — parenthèses,
#: apostrophes, points et virgules en clair, seuls les accents encodés.
_WIKI_SAFE = "_()',.!-~*"


def url_wikipedia(titre: str) -> str:
    """URL d'un article frwiki, encodée comme le corpus le fait.

    Mesuré : 49 URL Wikipédia du corpus sont en clair et 16 encodées, et les 16
    sont exactement celles dont le titre porte des accents — aucun titre accentué
    n'y est laissé en clair. `quote` n'encode donc que ce qui doit l'être, à
    condition de lui épargner la ponctuation que le corpus garde telle quelle.
    """
    return ("https://fr.wikipedia.org/wiki/"
            + urllib.parse.quote(titre.replace(" ", "_"), safe=_WIKI_SAFE))


#: propriété Wikidata → (source, fabricant d'URL à partir de la valeur rendue).
SOURCES_PAR_PROP: dict[str, tuple[Source, Any]] = {
    "P856": (SOURCE_SITE, _url_site),
    "P2003": (SOURCE_INSTAGRAM, _url_instagram),
    "P1266": (SOURCE_ALLOCINE, _url_allocine),
    "P345": (SOURCE_IMDB, _url_imdb),
}


@dataclass(frozen=True)
class Entite:
    """Ce que Wikidata dit d'une entité, réduit à ce dont la passe a besoin."""

    qid: str
    label: str = ""
    alias: tuple[str, ...] = ()
    natures: tuple[str, ...] = ()
    frwiki: str | None = None
    claims: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def valeur(self, prop: str) -> str | None:
        valeurs = self.claims.get(prop) or ()
        return valeurs[0] if valeurs else None


@dataclass(frozen=True)
class Lien:
    """Un lien prêt à écrire, et la source qui l'a rendu."""

    source: str
    kind: str
    ethics: str
    label: str
    url: str

    def as_link(self) -> dict[str, str]:
        return {"kind": self.kind, "ethics": self.ethics,
                "label": self.label, "url": self.url}


@dataclass(frozen=True)
class Resolution:
    """Le sort d'une reco : ses liens, la raison, et par quoi elle est prouvée."""

    liens: tuple[Lien, ...]
    raison: str
    preuve: str | None = None
    qid: str | None = None
    detail: str = ""


def hote(url: str) -> str:
    """Hôte d'une URL, en minuscules et sans `www.` (comparaison de liens).

    Chaque passe a le sien (cf. `music_links_matching.link_host`,
    `video_links_matching.link_host`) : le partager demanderait de déplacer ce
    quatre-lignes dans `common`, donc de toucher des modules qu'un autre
    chantier modifie en parallèle.
    """
    reste = url.split("//", 1)[-1]
    return reste.split("/", 1)[0].lower().removeprefix("www.")


def type_servi(reco: dict[str, Any]) -> str | None:
    """Premier type de la reco que cette passe sait traiter, sinon None."""
    for t in reco.get("types") or []:
        if t in TYPES_SERVIS:
            return t
    return None


def identifiants_portes(reco: dict[str, Any]) -> dict[str, str]:
    """Identifiants Deezer / Spotify que la reco porte DÉJÀ, par propriété.

    Deux gisements : `externalIds.deezer` (une URL, parfois un identifiant nu) et
    les liens déjà posés. Ce sont eux qui donnent la preuve la plus forte, et le
    seul moyen de retrouver une personne dont l'article n'a pas le titre attendu
    (« Yoa (artiste) » et non « Yoa »).
    """
    trouves: dict[str, str] = {}
    brut = str((reco.get("externalIds") or {}).get("deezer") or "")
    if m := _RE_DEEZER_ARTISTE.search(brut):
        trouves[PROP_DEEZER] = m.group(1)
    elif brut.isdigit():
        trouves[PROP_DEEZER] = brut
    for entree in reco.get("links") or []:
        url = str(entree.get("url") or "")
        if PROP_DEEZER not in trouves and (m := _RE_DEEZER_ARTISTE.search(url)):
            trouves[PROP_DEEZER] = m.group(1)
        if PROP_SPOTIFY not in trouves and (m := _RE_SPOTIFY_ARTISTE.search(url)):
            trouves[PROP_SPOTIFY] = m.group(1)
    return trouves


def noms_de_lentite(entite: Entite) -> set[str]:
    """Libellé et alias français, normalisés — de quoi comparer à un titre."""
    return {normalize_text(n) for n in (entite.label, *entite.alias) if n}


def liens_offerts(entite: Entite, reco: dict[str, Any]) -> list[Lien]:
    """Liens que l'entité permet de poser, hors hôtes déjà présents."""
    deja = {hote(str(e.get("url") or "")) for e in (reco.get("links") or [])}
    liens: list[Lien] = []
    for prop, (source, fabrique) in SOURCES_PAR_PROP.items():
        valeur = entite.valeur(prop)
        url = fabrique(valeur) if valeur else None
        if url and hote(url) not in deja:
            liens.append(Lien(source.nom, source.kind, source.ethics,
                              source.label, url))
            deja.add(hote(url))
    if entite.frwiki:
        url = url_wikipedia(entite.frwiki)
        if hote(url) not in deja:
            liens.append(Lien(SOURCE_WIKIPEDIA.nom, SOURCE_WIKIPEDIA.kind,
                              SOURCE_WIKIPEDIA.ethics, SOURCE_WIKIPEDIA.label, url))
    return liens


def verdict(reco: dict[str, Any],
            candidats: Sequence[tuple[Entite, str]]) -> Resolution:
    """Décide : quels liens, ou pourquoi aucun. Aucun réseau.

    `candidats` est une liste de (entité, preuve). Un même QID trouvé par les
    deux chemins garde la preuve la plus forte, l'identifiant.
    """
    type_ = type_servi(reco)
    if type_ is None:
        return Resolution((), RAISON_TYPE_UNSUPPORTED)

    entites: dict[str, Entite] = {}
    preuves: dict[str, str] = {}
    for entite, preuve in candidats:
        entites[entite.qid] = entite
        if preuves.get(entite.qid) != PREUVE_IDENTIFIANT:
            preuves[entite.qid] = preuve
    if not entites:
        return Resolution((), RAISON_NO_ENTITY)
    if len(entites) > 1:
        return Resolution((), RAISON_AMBIGUOUS, detail=" ".join(sorted(entites)))

    qid, entite = next(iter(entites.items()))
    preuve = preuves[qid]

    # Contradiction d'identifiants : un fait contre un fait, jamais une
    # ressemblance. Deux valeurs différentes sur la même propriété désignent
    # deux personnes, et ce refus vaut même quand l'identité venait d'un titre.
    for prop, valeur in identifiants_portes(reco).items():
        connues = entite.claims.get(prop)
        if connues and valeur not in connues:
            return Resolution((), RAISON_ID_MISMATCH, preuve, qid,
                              detail=f"{prop} reco={valeur} wikidata={connues[0]}")

    if preuve == PREUVE_TITRE:
        # Le titre d'article ne prouve rien : « Yoa » est un village du Cameroun.
        if normalize_text(reco.get("title")) not in noms_de_lentite(entite):
            return Resolution((), RAISON_LABEL_MISMATCH, preuve, qid,
                              detail=entite.label)
        if not (set(entite.natures) & NATURES_ADMISES[type_]):
            return Resolution((), RAISON_TYPE_INCOMPATIBLE, preuve, qid,
                              detail=",".join(entite.natures) or "sans P31")
    # Preuve par identifiant : l'identité est acquise. Exiger en plus une nature
    # connue ferait perdre un lien juste pour une fiche Wikidata incomplète.

    liens = liens_offerts(entite, reco)
    if not liens:
        return Resolution((), RAISON_NO_NEW_LINK, preuve, qid)
    return Resolution(tuple(liens), RAISON_OK, preuve, qid)
