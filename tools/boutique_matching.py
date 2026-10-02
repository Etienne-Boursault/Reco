"""Appariement pur de la passe « boutique » : où se procurer un jeu ou un livre.

Aucun réseau, aucun disque — c'est ici qu'on décide SI un candidat correspond.
Le réseau et la boucle vivent dans `boutique_links` (cf. `wikidata_matching` /
`wikidata_links`, même découpage).

RÈGLE FONDATRICE — ZÉRO INVENTION
---------------------------------
Reprise de l'en-tête d'`enrich_music_links`, et elle vaut ici autant : une URL
n'est écrite que si une source l'a RENVOYÉE et que sa réponse corrobore le titre
ET le studio (jeux) ou l'auteur (livres). Jamais d'URL fabriquée à partir d'un
titre, jamais de premier résultat retenu par défaut. Au moindre doute, aucun
lien, avec une raison traçable.

TROIS PIÈGES MESURÉS, que ce module existe pour verrouiller
----------------------------------------------------------
1. **Steam répond parfois sous la clé d'un AUTRE identifiant.** Mesuré le
   2026-09-27 : `appdetails?appids=2521170` (Looking For Fael) renvoie
   `{"4943810": {...}}` — l'identifiant de sa bande-son, que la fiche liste dans
   `dlc`. Lire `reponse[str(appid)]` rend donc `None`, la reco repart sans lien
   et SANS erreur : un faux négatif silencieux. `fiche_demandee` lit l'entrée
   UNIQUE et vérifie `data.steam_appid` à l'intérieur.
2. **`storesearch` étiquette tout en `type: "app"`** — DLC, démos et bandes-son
   comprises. Le seul type utile vient d'`appdetails` (`game`, `music`, `dlc`,
   `demo`). Sans ce filtre, « Looking For Fael Soundtrack » passait pour le jeu.
3. **Un titre de jeu seul ne prouve rien.** « The Witness » ramène aussi « City
   Legends: Le Témoin Dans le Seigle » et ses trois déclinaisons. L'égalité
   stricte du titre les écarte, mais deux vrais jeux peuvent porter le même nom :
   d'où l'exigence du studio, et le refus `ambiguous` quand plusieurs fiches
   survivent.

PLACE DES LIBRAIRES : LE SITE DONNE SON URL, ON NE LA FABRIQUE PAS
-----------------------------------------------------------------
Mesuré le 2026-09-28. Demander `/livre/<EAN>/` fait rediriger le site vers
l'URL complète `/livre/<EAN>-<slug>/`, qu'il déclare aussi en `rel="canonical"`,
et son JSON-LD porte l'ISBN. On écrit donc l'URL que le site a RÉSOLUE : un slug
fabriqué de notre côté serait une supposition, pas une source — et le slug ne
sert à rien, l'EAN suffit à résoudre la fiche. Un EAN inconnu répond 404, rejet
franc. À noter pour la prochaine session : `curl` s'était fait refuser (403)
depuis Windows, ce qui avait fait croire le site inutilisable ; il répond très
bien en Python, avec l'agent de l'outil comme avec celui d'un navigateur.

POURQUOI LE CRÉATEUR EST EXIGÉ
------------------------------
Comme en musique (`no-creator-to-verify`) : sans studio ni auteur, il n'y a rien
contre quoi corroborer, et le titre seul fait entrer un homonyme. Le corpus s'y
prête — 94 des 99 livres actifs portent leur auteur — mais seulement 16 des 34
jeux portent leur studio. L'option `--jeux-sans-studio` ouvre ce cas sous la
responsabilité de l'humain, et uniquement quand UNE seule fiche survit (même
esprit que l'opt-in `--artists` de la passe musicale).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from common import normalize_text

# Seuil et découpage des noms CALIBRÉS SUR MESURE RÉELLE dans la passe musicale
# (cf. `ARTIST_MATCH_THRESHOLD`, mesures des 2026-07-31 et 2026-09-25 sur les 895
# noms du corpus). En écrire d'autres ici reviendrait à recalibrer à l'aveugle —
# ce sont des helpers purs, et `video_links_report` importe déjà de la même façon
# les garde-fous calibrés d'`enrich_creators`.
from music_links_matching import creator_names, names_match, titles_match_strict

TYPE_JEU = "jeu"
TYPE_LIVRE = "livre"
#: Types que cette passe sait traiter.
TYPES_SERVIS: tuple[str, ...] = (TYPE_JEU, TYPE_LIVRE)

#: Seul `game` est le jeu lui-même : `music` est sa bande-son, `dlc` une
#: extension, `demo` un essai. Aucun des trois n'est ce que la reco recommande.
TYPE_STEAM_JEU = "game"

#: Nombre maximum de fiches Steam interrogées pour une reco. La recherche rend
#: jusqu'à 10 résultats et `appdetails` est strictement limité en débit : au-delà
#: des premiers candidats au titre identique, il n'y a plus rien à gagner.
MAX_FICHES_STEAM = 4
#: Nombre maximum d'EAN essayés pour un livre. Open Library rend jusqu'à 16 ISBN
#: pour une œuvre (éditions et traductions mêlées, l'allemande incluse pour
#: « Les vaisseaux du cœur ») : c'est la fiche libraire qui tranche, mais on ne
#: lui envoie pas 16 requêtes.
MAX_EAN_ESSAYES = 5

RAISON_OK = "ok"
RAISON_NOT_VALIDATED = "not-validated"
RAISON_TYPE_UNSUPPORTED = "type-unsupported"
RAISON_UNREADABLE = "unreadable"
RAISON_NO_CREATOR = "no-creator-to-verify"
RAISON_DEJA_SERVIE = "no-new-link"
#: « Je n'ai pas pu demander » — jamais confondu avec « ça n'existe pas ».
RAISON_HTTP_ERROR = "http-error"
RAISON_NO_MATCH = "no-match"
RAISON_AMBIGUOUS = "ambiguous"
RAISON_PAS_UN_JEU = "steam-not-a-game"
RAISON_STEAM_ID_MISMATCH = "steam-appid-mismatch"
RAISON_STUDIO_MISMATCH = "studio-mismatch"
RAISON_NO_ISBN = "no-isbn-found"
RAISON_EAN_ABSENT = "isbn-page-absent"
RAISON_PAGE_MISMATCH = "page-mismatch"

#: Refus qui demandent un arbitrage humain, par opposition à ceux qui constatent
#: une absence. Même rôle que `AMBIGUOUS_REASONS` côté musique.
RAISONS_A_ARBITRER = frozenset({
    RAISON_AMBIGUOUS, RAISON_STUDIO_MISMATCH, RAISON_PAGE_MISMATCH,
    RAISON_STEAM_ID_MISMATCH,
})


@dataclass(frozen=True)
class Source:
    """Une boutique, et la forme que ses liens prennent dans le corpus."""

    nom: str
    kind: str
    ethics: str
    label: str


#: Formes relevées dans le corpus avant d'écrire la moindre ligne : 18 liens
#: Steam en `buy`/`neutral` et 67 Place des Libraires en `buy`/`indie`.
SOURCE_STEAM = Source("steam", "buy", "neutral", "Steam")
SOURCE_LIBRAIRE = Source("place-des-libraires", "buy", "indie",
                         "Place des Libraires")
SOURCES_PAR_TYPE: dict[str, Source] = {TYPE_JEU: SOURCE_STEAM,
                                       TYPE_LIVRE: SOURCE_LIBRAIRE}

HOTE_STEAM = "store.steampowered.com"
HOTE_LIBRAIRE = "placedeslibraires.fr"
HOTES_PAR_SOURCE: dict[str, str] = {SOURCE_STEAM.nom: HOTE_STEAM,
                                    SOURCE_LIBRAIRE.nom: HOTE_LIBRAIRE}


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

    liens: tuple[Lien, ...] = ()
    raison: str = RAISON_NO_MATCH
    preuve: str | None = None
    isbn: str | None = None
    detail: str = ""


def hote(url: str) -> str:
    """Hôte d'une URL, en minuscules et sans `www.`.

    Chaque passe a le sien (cf. `music_links_matching.link_host`,
    `wikidata_matching.hote`) : partager ces quatre lignes demanderait de
    déplacer la fonction dans `common`, donc de toucher des modules que d'autres
    chantiers modifient en parallèle.
    """
    reste = url.split("//", 1)[-1]
    return reste.split("/", 1)[0].lower().removeprefix("www.")


def type_servi(reco: dict[str, Any]) -> str | None:
    """Premier type de la reco que cette passe sait traiter, sinon None."""
    for t in reco.get("types") or []:
        if t in TYPES_SERVIS:
            return t
    return None


def source_pour(reco: dict[str, Any]) -> Source | None:
    """La boutique qui correspond au type de la reco."""
    type_ = type_servi(reco)
    return SOURCES_PAR_TYPE.get(type_) if type_ else None


def deja_servie(reco: dict[str, Any], source: Source) -> bool:
    """True si la reco porte DÉJÀ un lien vers cette boutique.

    On ne remplace jamais un lien existant : la passe ne comble qu'une absence.
    """
    attendu = HOTES_PAR_SOURCE[source.nom]
    return any(hote(str(lien.get("url") or "")).endswith(attendu)
               for lien in reco.get("links") or [])


#: Mots qui ne désignent à eux seuls aucun studio. Sans cette liste, découper
#: notre `creator` sur les virgules faisait correspondre « Thekla, Inc. » à
#: « Autre chose, Inc. » par leur seul « Inc. ».
_MOTS_NON_IDENTIFIANTS = frozenset({
    "inc", "llc", "ltd", "limited", "sa", "sas", "sarl", "gmbh", "bv", "ab",
    "oy", "srl", "co", "corp", "corporation", "company", "games", "game",
    "studio", "studios", "entertainment", "interactive", "productions",
})


def _identifie_un_studio(nom: str | None) -> bool:
    """True si ce fragment peut à lui seul désigner un studio."""
    mots = [m for m in normalize_text(nom).split()
            if m not in _MOTS_NON_IDENTIFIANTS]
    return bool(mots)


def studio_correspond(noms_distants: list[str], creator: str | None) -> bool:
    """True si un studio ou éditeur renvoyé par Steam correspond au `creator`.

    Steam rend `developers` ET `publishers`, chacun déjà séparé : il suffit que
    l'un corresponde. « Looking For Fael » est développé par Swing Swing
    Submarine et La Poule Noire, publié par ARTE France, et le corpus peut nommer
    l'un ou l'autre.

    La chaîne ENTIÈRE est essayée avant ses fragments, parce qu'une virgule
    sépare deux studios dans notre champ (« Swing Swing Submarine, La Poule
    Noire ») mais appartient aussi à certaines raisons sociales (« Thekla,
    Inc. »). Et un fragment qui ne désigne personne — « Inc. », « Studios » — ne
    peut pas valider à lui seul, sans quoi deux sociétés sans rapport
    correspondraient (mesuré en écrivant ces tests).
    """
    locaux = [creator or "", *creator_names(creator)]
    return any(names_match(distant, local)
               for distant in noms_distants for local in locaux
               if _identifie_un_studio(local))


def auteur_correspond(auteurs: list[str], creator: str | None) -> bool:
    """True si un auteur renvoyé par une source bibliographique correspond.

    Le découpage est SYMÉTRIQUE, comme `artist_matches_creator` côté musique : la
    fiche d'un livre à quatre mains nomme ses deux auteurs d'un bloc (« Bruno
    Muschio, Kyan Khojandi » pour *Bref. 2, le livre*) quand le corpus écrit
    « Kyan Khojandi, Navo ». Comparer les chaînes entières donnait 0,65 pour 0,88
    requis — un refus injustifié, mesuré le 2026-10-02. Découper des deux côtés
    est sans risque ici : une virgule sépare des personnes, elle n'appartient pas
    à leur nom (contrairement aux raisons sociales, cf. `studio_correspond`).
    """
    locaux = creator_names(creator)
    return any(names_match(distant, local)
               for auteur in auteurs for distant in creator_names(auteur)
               for local in locaux)


def fiche_demandee(payload: dict[str, Any], appid: int) -> dict[str, Any] | None:
    """La fiche `appdetails` correspondant à `appid`, ou None.

    ⚠️ Ne lit PAS `payload[str(appid)]` : Steam répond parfois sous la clé d'un
    autre identifiant (cf. l'en-tête du module). On lit les entrées présentes et
    on retient celle dont `data.steam_appid` est bien l'identifiant demandé —
    la seule affirmation de Steam qui porte sur le jeu lui-même.
    """
    for bloc in payload.values():
        if not isinstance(bloc, dict) or not bloc.get("success"):
            continue
        data = bloc.get("data")
        if isinstance(data, dict) and data.get("steam_appid") == appid:
            return data
    return None


def studios_de(data: dict[str, Any]) -> list[str]:
    """Studios et éditeurs d'une fiche Steam, sans trous ni doublons."""
    noms: list[str] = []
    for champ in ("developers", "publishers"):
        for nom in data.get(champ) or []:
            if isinstance(nom, str) and nom.strip() and nom not in noms:
                noms.append(nom.strip())
    return noms


def url_steam(appid: int) -> str:
    """Page boutique d'un jeu — forme des 18 liens Steam déjà au corpus."""
    return f"https://store.steampowered.com/app/{appid}/"


_RE_TITRE_PAGE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_RE_CANONIQUE = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE)
_RE_JSONLD_ISBN = re.compile(r'"isbn"\s*:\s*"([0-9Xx-]{10,20})"')


def fiche_libraire(html: str) -> tuple[str, str, str]:
    """(titre, auteur, éditeur) lus dans le `<title>` de Place des Libraires.

    Leur gabarit est « Titre - Auteur - Éditeur » (« Les solitudes de Petite
    Rivière - Kalindi Ramphul - JC Lattès »). Les parties manquantes reviennent
    vides, et l'appelant refuse alors : une page qui ne nomme pas son auteur ne
    corrobore rien.
    """
    trouve = _RE_TITRE_PAGE.search(html)
    if not trouve:
        return "", "", ""
    morceaux = [m.strip() for m in trouve.group(1).split(" - ")]
    while len(morceaux) < 3:
        morceaux.append("")
    return morceaux[0], morceaux[1], " - ".join(morceaux[2:]).strip()


def isbn_de_page(html: str) -> str | None:
    """ISBN déclaré par le JSON-LD de la page, s'il y est."""
    trouve = _RE_JSONLD_ISBN.search(html)
    return trouve.group(1).replace("-", "") if trouve else None


def url_canonique(html: str, url_resolue: str) -> str:
    """L'URL que le site déclare pour cette page, sinon celle qu'il a résolue.

    Les deux sont la même chose sur Place des Libraires (vérifié le 2026-09-28) ;
    on préfère la déclaration explicite, et l'URL résolue reste un repli — dans
    les deux cas, elle vient du site, pas de nous.
    """
    trouve = _RE_CANONIQUE.search(html)
    return trouve.group(1).strip() if trouve else url_resolue


def page_corrobore(html: str, titre: str, creator: str | None) -> bool:
    """True si la page libraire nomme bien CE livre et SON auteur.

    Titre : égalité stricte après normalisation, comme en musique — la moindre
    permissivité fait entrer un homonyme. Auteur : comparaison tolérante aux
    accents et aux fautes de transcription (`names_match`).
    """
    titre_page, auteur_page, _ = fiche_libraire(html)
    if not titre_page or not auteur_page:
        return False
    return (titres_correspondent(titre_page, titre)
            and auteur_correspond([auteur_page], creator))


def titres_correspondent(a: str | None, b: str | None) -> bool:
    """Égalité de titres après normalisation (accents, casse, ponctuation)."""
    return titles_match_strict(a, b)


def candidats_au_bon_titre(items: list[dict[str, Any]],
                           titre: str) -> list[tuple[int, str]]:
    """Résultats de recherche Steam dont le nom EST le titre de la reco.

    C'est ce filtre qui écarte « Looking For Fael Soundtrack » et les quatre
    « City Legends: Le Témoin… » rendus pour « The Witness ».
    """
    gardes: list[tuple[int, str]] = []
    for item in items:
        nom = str(item.get("name") or "")
        appid = item.get("id")
        if isinstance(appid, int) and titres_correspondent(nom, titre):
            gardes.append((appid, nom))
    return gardes[:MAX_FICHES_STEAM]


def eans_valides(brut: list[str]) -> list[str]:
    """ISBN-13 plausibles, dédoublonnés, dans l'ordre reçu.

    On ne garde que la forme à 13 chiffres : Place des Libraires ne résout que
    celle-là, et un ISBN-10 renvoyé par Open Library donnerait un 404 trompeur.
    """
    vus: list[str] = []
    for valeur in brut:
        ean = re.sub(r"[^0-9]", "", str(valeur or ""))
        if len(ean) == 13 and ean not in vus:
            vus.append(ean)
    return vus[:MAX_EAN_ESSAYES]


def volume_corrobore(volume: dict[str, Any], titre: str,
                     creator: str | None) -> list[str]:
    """ISBN-13 d'un volume Google Books, s'il parle bien de CE livre.

    Le payload porte `title` et `authors` : de quoi corroborer avant de retenir
    le moindre identifiant. Sans corroboration, liste vide.
    """
    info = volume.get("volumeInfo") or {}
    auteurs = [a for a in info.get("authors") or [] if isinstance(a, str)]
    if not titres_correspondent(str(info.get("title") or ""), titre):
        return []
    if not auteur_correspond(auteurs, creator):
        return []
    return eans_valides([x.get("identifier", "")
                         for x in info.get("industryIdentifiers") or []
                         if x.get("type") == "ISBN_13"])


def documents_corrobores(docs: list[dict[str, Any]], titre: str,
                         creator: str | None) -> list[str]:
    """ISBN candidats d'Open Library, pour les seules œuvres corroborées.

    ⚠️ Open Library rend les ISBN de TOUTES les éditions d'une œuvre, traductions
    comprises : ce ne sont que des CANDIDATS, et c'est la fiche libraire qui
    tranchera. Le titre et l'auteur sont tout de même vérifiés ici, pour ne pas
    envoyer au libraire les éditions d'un homonyme.
    """
    candidats: list[str] = []
    for doc in docs:
        auteurs = [a for a in doc.get("author_name") or [] if isinstance(a, str)]
        if not titres_correspondent(str(doc.get("title") or ""), titre):
            continue
        if not auteur_correspond(auteurs, creator):
            continue
        candidats.extend(str(i) for i in doc.get("isbn") or [])
    return eans_valides(candidats)


_RE_EAN_RESULTAT = re.compile(r"/livre/(\d{13})-[a-z0-9-]+/")


def eans_de_resultats(html: str) -> list[str]:
    """EAN-13 des fiches listées par une page de résultats du libraire.

    Ce ne sont que des CANDIDATS : la fiche de chacun sera ouverte et devra
    corroborer titre et auteur. La recherche du libraire est pourtant la source
    la plus pertinente pour une parution française récente — mesuré le
    2026-10-02 : elle rend les bons EAN des deux livres de 2026 que Google Books
    (429) et Open Library (absents de son catalogue) ne savaient pas donner.
    """
    vus: list[str] = []
    for ean in _RE_EAN_RESULTAT.findall(html):
        if ean not in vus:
            vus.append(ean)
    return vus[:MAX_EAN_ESSAYES]


def jsonld_isbn_coherent(html: str, ean: str) -> bool:
    """True si la page ne contredit pas l'EAN demandé.

    Le JSON-LD de Place des Libraires porte l'ISBN de la fiche. S'il diffère de
    l'EAN demandé, la redirection nous a menés ailleurs : on refuse. Absent, on
    ne conclut rien — le titre et l'auteur corroborent déjà.
    """
    declare = isbn_de_page(html)
    return declare is None or declare == ean


def _normalise(valeur: str | None) -> str:
    """Exposé pour les tests : la normalisation utilisée par les comparaisons."""
    return normalize_text(valeur)


def resolution_json(resolution: Resolution) -> str:
    """Représentation compacte d'une résolution (journal, mises au point)."""
    return json.dumps({"raison": resolution.raison,
                       "liens": [lien.url for lien in resolution.liens],
                       "preuve": resolution.preuve,
                       "isbn": resolution.isbn},
                      ensure_ascii=False)
