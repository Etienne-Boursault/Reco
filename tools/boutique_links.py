"""Réseau et boucle de la passe « boutique » : Steam pour les jeux, libraire
pour les livres.

Les décisions sont dans `boutique_matching` (aucun réseau) ; ici on interroge,
on résout, on écrit. Même découpage que `wikidata_matching` / `wikidata_links`.

TOUT LE RÉSEAU PASSE PAR `_demander`
------------------------------------
Un seul point de sortie, pour qu'un test puisse le neutraliser d'un seul coup
(cf. `tests/enrich_boutique_links/conftest.py`). Le dépôt s'est déjà fait
prendre : la fixture qui mettait TMDB hors ligne ne couvrait qu'une des deux
passes, et des tests partaient chercher la vraie clé en se contentant d'un
avertissement.

« PAS PU DEMANDER » N'EST PAS « N'EXISTE PAS »
---------------------------------------------
`BoutiqueInjoignable` est typée pour cette raison. Un 429 de Google Books — que
l'API rend volontiers, mesuré le 2026-09-28 — ne dit rien sur le livre ; conclure
« pas d'ISBN » un jour de limitation salirait le rapport et ferait renoncer à la
main. Les deux cas ont donc deux raisons distinctes, et `run` rattrape l'exception
reco par reco : la passe continue.

SOURCES
-------
  - **Steam** — `storesearch` (sans clé) pour trouver, `appdetails` pour
    corroborer : c'est la seule des deux qui donne le TYPE réel et les studios.
    Ses pièges sont documentés dans `boutique_matching`.
  - **Google Books** — ISBN-13 avec titre et auteurs dans la même réponse, de
    quoi corroborer. Limite de débit stricte (429 fréquent, sans clé).
  - **Open Library** — second avis, indépendant. Rend les ISBN de toutes les
    éditions d'une œuvre : des candidats, pas une réponse.
  - **Place des Libraires** — sa RECHERCHE propose des EAN (seule source qui
    connaisse les parutions françaises récentes), et sa FICHE juge en dernier
    ressort : titre, auteur et ISBN doivent y concorder.
"""
from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import requests

from boutique_matching import (
    MAX_EAN_ESSAYES,
    RAISON_AMBIGUOUS,
    RAISON_DEJA_SERVIE,
    RAISON_EAN_ABSENT,
    RAISON_HTTP_ERROR,
    RAISON_NO_CREATOR,
    RAISON_NO_ISBN,
    RAISON_NO_MATCH,
    RAISON_NOT_VALIDATED,
    RAISON_OK,
    RAISON_PAGE_MISMATCH,
    RAISON_PAS_UN_JEU,
    RAISON_STEAM_ID_MISMATCH,
    RAISON_STUDIO_MISMATCH,
    RAISON_UNREADABLE,
    SOURCE_LIBRAIRE,
    SOURCE_STEAM,
    TYPE_JEU,
    TYPE_STEAM_JEU,
    Lien,
    Resolution,
    candidats_au_bon_titre,
    creator_names,
    deja_servie,
    documents_corrobores,
    eans_de_resultats,
    eans_valides,
    fiche_demandee,
    hote,
    jsonld_isbn_coherent,
    page_corrobore,
    source_pour,
    studio_correspond,
    studios_de,
    type_servi,
    url_canonique,
    url_steam,
    volume_corrobore,
)
from boutique_report import Cas, RapportBoutique
from common import log, read_json, write_json_if_changed
from enrichment.field_refresher import (
    EnrichedAtCorruptedError,
    partial_update,
    update_nested,
)
from enrichment.tracker import now_iso
from music_links_pipeline import iter_reco_paths

STEAM_RECHERCHE = "https://store.steampowered.com/api/storesearch/"
STEAM_FICHE = "https://store.steampowered.com/api/appdetails"
GOOGLE_BOOKS = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY = "https://openlibrary.org/search.json"
LIBRAIRE_FICHE = "https://www.placedeslibraires.fr/livre/{ean}/"
LIBRAIRE_RECHERCHE = "https://www.placedeslibraires.fr/listeliv.php"

#: Agent explicite et joignable : ces APIs sont publiques et sans clé, c'est la
#: moindre des politesses, et Steam limite les clients anonymes trop rapides.
USER_AGENT = "reco-liens-boutique/1.0 (+https://github.com/Etienne-Boursault/Reco)"
HTTP_TIMEOUT = 25
HTTP_TOO_MANY_REQUESTS = 429
HTTP_NOT_FOUND = 404
#: Pause entre deux recos.
PAUSE = 0.5
#: Pause entre deux fiches Steam : `appdetails` est bien plus sévèrement limité
#: que la recherche (quelques centaines d'appels par tranche de cinq minutes).
PAUSE_STEAM = 1.5


class BoutiqueInjoignable(RuntimeError):
    """Une source ne répond pas (429, panne, réponse illisible).

    Typée parce que « rien trouvé » et « pas pu demander » n'ont pas le même
    sens (cf. l'en-tête du module).
    """


def _demander(session: requests.Session, url: str,
              params: dict[str, Any] | None = None) -> requests.Response:
    """Un appel HTTP. Lève `BoutiqueInjoignable` si la source se dérobe.

    Un 404 n'est PAS une dérobade : c'est une réponse, et elle veut dire que la
    fiche n'existe pas. Il revient donc à l'appelant.
    """
    try:
        reponse = session.get(url, params=params or {},
                              headers={"User-Agent": USER_AGENT,
                                       "Accept-Language": "fr"},
                              timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise BoutiqueInjoignable(f"injoignable ({exc})") from exc
    if reponse.status_code == HTTP_TOO_MANY_REQUESTS:
        raise BoutiqueInjoignable("limite d'appels atteinte (429)")
    if reponse.status_code not in (200, HTTP_NOT_FOUND):
        raise BoutiqueInjoignable(f"HTTP {reponse.status_code}")
    return reponse


def _json(reponse: requests.Response) -> dict[str, Any]:
    """Corps JSON d'une réponse, ou `BoutiqueInjoignable` si elle est illisible."""
    try:
        charge = reponse.json()
    except ValueError as exc:
        raise BoutiqueInjoignable("réponse illisible") from exc
    return charge if isinstance(charge, dict) else {}


# ===========================================================================
# Clients
# ===========================================================================
def steam_candidats(session: requests.Session, titre: str) -> list[dict[str, Any]]:
    """Résultats bruts de la recherche Steam (`items`)."""
    reponse = _demander(session, STEAM_RECHERCHE,
                        {"cc": "fr", "l": "fr", "term": titre})
    items = _json(reponse).get("items")
    return [it for it in items if isinstance(it, dict)] if isinstance(items, list) else []


def steam_fiche(session: requests.Session, appid: int) -> dict[str, Any] | None:
    """Fiche `appdetails` de CE jeu, ou None si Steam ne la sert pas.

    Le tri par `steam_appid` est fait par `fiche_demandee` : Steam répond parfois
    sous la clé d'un autre identifiant (cf. `boutique_matching`).
    """
    reponse = _demander(session, STEAM_FICHE,
                        {"appids": appid, "cc": "fr", "l": "fr"})
    return fiche_demandee(_json(reponse), appid)


def isbn_google(session: requests.Session, titre: str,
                creator: str | None) -> list[str]:
    """ISBN-13 proposés par Google Books, titre et auteur corroborés."""
    requete = f'intitle:"{titre}"'
    if creator:
        requete += f' inauthor:"{creator}"'
    reponse = _demander(session, GOOGLE_BOOKS,
                        {"q": requete, "country": "FR", "maxResults": 5})
    volumes = _json(reponse).get("items")
    if not isinstance(volumes, list):
        return []
    trouves: list[str] = []
    for volume in volumes:
        if isinstance(volume, dict):
            trouves.extend(volume_corrobore(volume, titre, creator))
    return eans_valides(trouves)


def isbn_openlibrary(session: requests.Session, titre: str,
                     creator: str | None) -> list[str]:
    """ISBN candidats proposés par Open Library, titre et auteur corroborés."""
    params = {"title": titre, "limit": 3,
              "fields": "title,author_name,isbn,publisher,first_publish_year"}
    if creator:
        params["author"] = creator
    reponse = _demander(session, OPEN_LIBRARY, params)
    docs = _json(reponse).get("docs")
    if not isinstance(docs, list):
        return []
    return documents_corrobores([d for d in docs if isinstance(d, dict)],
                                titre, creator)


def isbn_libraire(session: requests.Session, titre: str,
                  creator: str | None) -> list[str]:
    """EAN candidats trouvés par la recherche du libraire lui-même.

    Source la plus pertinente pour une parution française récente, et la seule
    des trois qui connaissait les deux livres de 2026 du corpus (mesuré le
    2026-10-02). Elle ne fait que proposer : chaque EAN passera par sa fiche.
    """
    #: Le PREMIER nom de l'auteur, pas le champ entier : « Bref. 2, le livre Kyan
    #: Khojandi, Navo » ne rend AUCUN résultat, là où « … Kyan Khojandi » rend le
    #: bon EAN (mesuré le 2026-10-02). Le titre seul sert de repli : il rend
    #: parfois plusieurs livres, mais c'est la fiche qui tranche ensuite, donc
    #: élargir la recherche ne relâche aucun garde-fou.
    premier = next(iter(creator_names(creator)), "")
    requetes = [f"{titre} {premier}".strip(), titre] if premier else [titre]
    for mots in dict.fromkeys(requetes):
        reponse = _demander(session, LIBRAIRE_RECHERCHE, {"MOTS": mots})
        if reponse.status_code == HTTP_NOT_FOUND:
            continue
        eans = eans_de_resultats(reponse.text)
        if eans:
            return eans
    return []


def page_libraire(session: requests.Session,
                  ean: str) -> tuple[str, str] | None:
    """(url résolue, html) de la fiche libraire, ou None si l'EAN est inconnu.

    On demande `/livre/<EAN>/` : le site redirige vers l'URL complète, qui est
    celle qu'on écrira (cf. `boutique_matching`). Un 404 rend None.
    """
    reponse = _demander(session, LIBRAIRE_FICHE.format(ean=ean))
    if reponse.status_code == HTTP_NOT_FOUND:
        return None
    return str(reponse.url), reponse.text


# ===========================================================================
# Résolution
# ===========================================================================
def resoudre_jeu(reco: dict[str, Any], *, session: requests.Session,
                 permettre_sans_studio: bool = False,
                 pause: float = PAUSE_STEAM) -> Resolution:
    """Cherche la page Steam d'un jeu, et ne la retient que corroborée."""
    titre = str(reco.get("title") or "")
    creator = str(reco.get("creator") or "").strip()
    if not creator and not permettre_sans_studio:
        return Resolution(raison=RAISON_NO_CREATOR)

    candidats = candidats_au_bon_titre(steam_candidats(session, titre), titre)
    if not candidats:
        return Resolution(raison=RAISON_NO_MATCH)

    retenus: list[tuple[int, str]] = []
    refus = RAISON_NO_MATCH
    for index, (appid, nom) in enumerate(candidats):
        if index and pause:
            time.sleep(pause)
        fiche = steam_fiche(session, appid)
        if fiche is None:
            # Steam a répondu, mais pas sur ce jeu : on ne devine pas.
            refus = RAISON_STEAM_ID_MISMATCH
            continue
        if fiche.get("type") != TYPE_STEAM_JEU:
            refus = RAISON_PAS_UN_JEU
            continue
        studios = studios_de(fiche)
        if creator and not studio_correspond(studios, creator):
            refus = RAISON_STUDIO_MISMATCH
            continue
        retenus.append((appid, ", ".join(studios) or nom))

    if not retenus:
        return Resolution(raison=refus)
    if len(retenus) > 1:
        return Resolution(raison=RAISON_AMBIGUOUS,
                          detail=" / ".join(str(a) for a, _ in retenus))
    appid, preuve = retenus[0]
    lien = Lien(SOURCE_STEAM.nom, SOURCE_STEAM.kind, SOURCE_STEAM.ethics,
                SOURCE_STEAM.label, url_steam(appid))
    return Resolution(liens=(lien,), raison=RAISON_OK, preuve=preuve)


def resoudre_livre(reco: dict[str, Any], *, session: requests.Session,
                   pause: float = PAUSE) -> Resolution:
    """Cherche l'ISBN d'un livre, puis sa fiche libraire — qui tranche.

    Les deux sources d'ISBN sont interrogées l'une après l'autre, et une panne de
    la première ne doit pas faire renoncer : Google Books répond souvent 429.
    """
    titre = str(reco.get("title") or "")
    creator = str(reco.get("creator") or "").strip()
    if not creator:
        return Resolution(raison=RAISON_NO_CREATOR)

    # Le libraire d'abord : c'est lui qui connaît les parutions françaises
    # récentes, et son EAN tombe donc juste du premier coup le plus souvent.
    sources = (isbn_libraire, isbn_google, isbn_openlibrary)
    eans: list[str] = []
    pannes = 0
    for source in sources:
        try:
            for ean in source(session, titre, creator):
                if ean not in eans:
                    eans.append(ean)
        except BoutiqueInjoignable as exc:
            pannes += 1
            log.info("      %s : %s", source.__name__, exc)
    if not eans:
        # Aucune source n'a rien donné : si elles se sont TOUTES dérobées, c'est
        # le réseau qu'il faut incriminer, pas l'absence du livre.
        return Resolution(
            raison=RAISON_HTTP_ERROR if pannes == len(sources) else RAISON_NO_ISBN)

    refus = RAISON_EAN_ABSENT
    for index, ean in enumerate(eans[:MAX_EAN_ESSAYES]):
        if index and pause:
            time.sleep(pause)
        fiche = page_libraire(session, ean)
        if fiche is None:
            continue
        url_resolue, html = fiche
        if not jsonld_isbn_coherent(html, ean):
            refus = RAISON_PAGE_MISMATCH
            continue
        if not page_corrobore(html, titre, creator):
            refus = RAISON_PAGE_MISMATCH
            continue
        lien = Lien(SOURCE_LIBRAIRE.nom, SOURCE_LIBRAIRE.kind,
                    SOURCE_LIBRAIRE.ethics, SOURCE_LIBRAIRE.label,
                    url_canonique(html, url_resolue))
        return Resolution(liens=(lien,), raison=RAISON_OK, preuve=ean, isbn=ean)
    return Resolution(raison=refus)


def resoudre(reco: dict[str, Any], *, session: requests.Session,
             permettre_sans_studio: bool = False) -> Resolution:
    """Résout une reco selon son type. Ne touche jamais une source déjà posée."""
    source = source_pour(reco)
    if source is None:
        return Resolution(raison=RAISON_NO_MATCH)
    if deja_servie(reco, source):
        return Resolution(raison=RAISON_DEJA_SERVIE)
    if type_servi(reco) == TYPE_JEU:
        return resoudre_jeu(reco, session=session,
                            permettre_sans_studio=permettre_sans_studio)
    return resoudre_livre(reco, session=session)


# ===========================================================================
# Écriture, rapport, boucle
# ===========================================================================
def appliquer(reco: dict[str, Any], resolution: Resolution,
              *, timestamp: str | None = None) -> dict[str, Any]:
    """AJOUTE les liens et l'ISBN à la reco + l'audit trail, IN-PLACE.

    Un hôte déjà présent n'est jamais ajouté : garde-fou de dernier recours, la
    sélection l'ayant déjà écarté. L'ISBN va dans `externalIds.isbn`, que le
    schéma des recos accepte déjà — c'est un FAIT corroboré par la fiche, utile
    même le jour où le libraire change d'URL.
    """
    horodatage = timestamp or now_iso()
    existants = list(reco.get("links") or [])
    hotes = {hote(str(e.get("url") or "")) for e in existants}
    ajouts = [lien.as_link() for lien in resolution.liens
              if hote(lien.url) not in hotes]
    if ajouts:
        partial_update(reco, "links", existants + ajouts, timestamp=horodatage)
    if resolution.isbn and not (reco.get("externalIds") or {}).get("isbn"):
        update_nested(reco, "externalIds.isbn", resolution.isbn,
                      timestamp=horodatage)
    return reco


def run(*, root: Path, session: requests.Session | None = None,
        source: str | None = None, types: Sequence[str] | None = None,
        ids: Iterable[str] = (), limit: int | None = None,
        apply: bool = False, permettre_sans_studio: bool = False,
        sleep: float = PAUSE) -> RapportBoutique:
    """Passe complète : sélectionne, résout, journalise, écrit si `apply`.

    `ids` restreint aux seules recos citées — ce dont la chaîne a besoin pour ne
    traiter qu'un épisode fraîchement relu, sans rouvrir les 3 000 autres.
    """
    session = session or requests.Session()
    voulus = set(ids)
    filtre_types = set(types) if types else None
    rapport = RapportBoutique()
    resolues = 0

    for chemin in iter_reco_paths(root, source):
        try:
            reco = read_json(chemin)
        except (ValueError, OSError) as exc:
            log.warning("  %s illisible (%s) — ignoré", chemin.name, exc)
            rapport.cas.append(Cas(chemin.stem, "", "", RAISON_UNREADABLE))
            continue
        reco_id = str(reco.get("id", chemin.stem))
        type_ = type_servi(reco)
        if voulus and reco_id not in voulus:
            continue
        if type_ is None:
            continue
        if filtre_types and not (set(reco.get("types") or []) & filtre_types):
            continue
        rapport.vues += 1
        titre = str(reco.get("title") or "")

        if reco.get("status") != "validated":
            rapport.cas.append(Cas(reco_id, titre, type_, RAISON_NOT_VALIDATED))
            continue
        if limit is not None and resolues >= limit:
            continue

        try:
            resolution = resoudre(reco, session=session,
                                  permettre_sans_studio=permettre_sans_studio)
        except BoutiqueInjoignable as exc:
            log.info("  %s · %s → source injoignable : %s", reco_id, titre[:40], exc)
            rapport.cas.append(Cas(reco_id, titre, type_, RAISON_HTTP_ERROR,
                                   detail=str(exc)))
            continue
        resolues += 1
        rapport.cas.append(Cas(reco_id, titre, type_, resolution.raison,
                               resolution.preuve, len(resolution.liens),
                               resolution.detail))
        _journaliser(reco_id, titre, resolution)

        if resolution.liens and apply:
            try:
                appliquer(reco, resolution)
            except EnrichedAtCorruptedError as exc:
                log.error("  %s · audit trail corrompu (%s) — non écrit",
                          reco_id, exc)
                continue
            if write_json_if_changed(chemin, reco):
                rapport.ecrites += 1
        if sleep:
            time.sleep(sleep)

    return rapport


def _journaliser(reco_id: str, titre: str, resolution: Resolution) -> None:
    """Une ligne par reco : le lien trouvé, ou la raison du refus."""
    if resolution.liens:
        for lien in resolution.liens:
            log.info("  %s · %s → %s (%s)", reco_id, titre[:40], lien.url,
                     resolution.preuve or lien.source)
    else:
        detail = f" — {resolution.detail}" if resolution.detail else ""
        log.info("  %s · %s → aucun lien : %s%s", reco_id, titre[:40],
                 resolution.raison, detail)
