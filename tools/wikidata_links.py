"""Interroge Wikidata, résout une reco, déroule la passe et écrit.

Ce module fait les appels et l'écriture ; il ne décide de rien — les garde-fous
sont dans `wikidata_matching`, éprouvables sans réseau. La doctrine et les
mesures qui les justifient sont dans l'en-tête de `enrich_wikidata_links`.

Deux chemins d'identification, tous deux EXACTS (la recherche libre de Wikidata
n'est jamais utilisée, cf. la doctrine) :
  `entites_par_identifiant`  `haswbstatement` : quelle entité déclare cet
                             identifiant Deezer / Spotify — un fait.
  `entites_par_titres`       `wbgetentities&sites=frwiki` : le titre d'article
                             est une clé exacte, et 50 titres passent en un
                             appel, d'où l'absence de 429 à redouter.
"""
from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from common import log, normalize_text, read_json, write_json_if_changed
from enrich_creators import iter_reco_paths
from enrichment.field_refresher import EnrichedAtCorruptedError, partial_update
from enrichment.tracker import now_iso
from wikidata_matching import (
    PREUVE_IDENTIFIANT,
    PREUVE_TITRE,
    RAISON_HTTP_ERROR,
    RAISON_NOT_VALIDATED,
    RAISON_OK,
    RAISON_TYPE_UNSUPPORTED,
    RAISON_UNREADABLE,
    RAISONS_A_ARBITRER,
    Entite,
    Lien,
    Resolution,
    hote,
    identifiants_portes,
    type_servi,
    verdict,
)

API = "https://www.wikidata.org/w/api.php"
#: Wikidata bannit les clients anonymes trop rapides : un agent explicite et
#: joignable, plus une pause entre deux recos.
USER_AGENT = "reco-liens-wikidata/1.0 (+https://github.com/Etienne-Boursault/Reco)"
HTTP_TIMEOUT = 20
HTTP_TOO_MANY_REQUESTS = 429
RATE_LIMIT_SLEEP = 0.4
#: `wbgetentities` n'accepte pas plus de 50 titres par appel.
LOT_MAX = 50
_PROPS_LUES = "claims|sitelinks|labels|aliases"


class WikidataInjoignable(RuntimeError):
    """Wikidata n'a pas répondu (429, panne réseau, réponse illisible).

    Typée, parce que « rien trouvé » et « pas pu demander » n'ont pas le même
    sens : le premier est un fait sur la personne, le second sur le réseau. Les
    confondre ferait conclure qu'un artiste est absent de Wikidata un jour de
    coupure. `run` la rattrape reco par reco : la passe continue.
    """


def _get(session: requests.Session, params: dict[str, str]) -> dict[str, Any]:
    """Un appel à l'API Wikidata. Lève `WikidataInjoignable` si elle se dérobe."""
    try:
        reponse = session.get(API, params={**params, "format": "json"},
                              headers={"User-Agent": USER_AGENT},
                              timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise WikidataInjoignable(f"injoignable ({exc})") from exc
    if reponse.status_code == HTTP_TOO_MANY_REQUESTS:
        raise WikidataInjoignable("limite d'appels atteinte (429)")
    if reponse.status_code != 200:
        raise WikidataInjoignable(f"HTTP {reponse.status_code}")
    try:
        return reponse.json()
    except ValueError as exc:
        raise WikidataInjoignable("réponse illisible") from exc


def entite_depuis_json(qid: str, brut: dict[str, Any]) -> Entite:
    """Réduit la réponse de Wikidata à ce dont la passe a besoin."""
    claims: dict[str, tuple[str, ...]] = {}
    for prop, enonces in (brut.get("claims") or {}).items():
        valeurs = []
        for enonce in enonces:
            donnee = (enonce.get("mainsnak") or {}).get("datavalue", {}).get("value")
            if isinstance(donnee, dict):
                donnee = donnee.get("id")
            if isinstance(donnee, str) and donnee:
                valeurs.append(donnee)
        if valeurs:
            claims[prop] = tuple(valeurs)
    labels = brut.get("labels") or {}
    return Entite(
        qid=qid,
        label=str((labels.get("fr") or labels.get("en") or {}).get("value") or ""),
        alias=tuple(a.get("value", "")
                    for a in (brut.get("aliases") or {}).get("fr", [])),
        natures=claims.get("P31", ()),
        frwiki=((brut.get("sitelinks") or {}).get("frwiki") or {}).get("title"),
        claims=claims,
    )


def entites_par_titres(session: requests.Session,
                       titres: Sequence[str]) -> dict[str, Entite]:
    """Entités dont l'ARTICLE frwiki porte exactement l'un de ces titres."""
    trouvees: dict[str, Entite] = {}
    voulus = [t for t in dict.fromkeys(titres) if t]
    for debut in range(0, len(voulus), LOT_MAX):
        lot = voulus[debut:debut + LOT_MAX]
        donnees = _get(session, {"action": "wbgetentities", "sites": "frwiki",
                                 "props": _PROPS_LUES, "languages": "fr|en",
                                 "titles": "|".join(lot)})
        for qid, brut in (donnees.get("entities") or {}).items():
            if "missing" in brut:
                continue
            entite = entite_depuis_json(qid, brut)
            for titre in lot:
                if entite.frwiki and normalize_text(entite.frwiki) == normalize_text(titre):
                    trouvees[titre] = entite
    return trouvees


def entites_par_identifiant(session: requests.Session, prop: str,
                            valeur: str) -> list[Entite]:
    """Entités qui DÉCLARENT `prop = valeur` (`haswbstatement`).

    Deux entités pour un même identifiant est une incohérence de Wikidata : on
    les rend toutes, et le verdict refusera pour ambiguïté plutôt que trancher.
    """
    donnees = _get(session, {"action": "query", "list": "search", "srnamespace": "0",
                             "srlimit": "3",
                             "srsearch": f"haswbstatement:{prop}={valeur}"})
    qids = [r["title"] for r in (donnees.get("query") or {}).get("search", [])
            if str(r.get("title", "")).startswith("Q")]
    if not qids:
        return []
    detail = _get(session, {"action": "wbgetentities", "props": _PROPS_LUES,
                            "languages": "fr|en", "ids": "|".join(qids)})
    return [entite_depuis_json(qid, brut)
            for qid, brut in (detail.get("entities") or {}).items()
            if "missing" not in brut]


def resoudre(reco: dict[str, Any], *, session: requests.Session) -> Resolution:
    """Cherche l'entité — identifiant d'abord, titre ensuite — puis tranche.

    L'ordre n'est pas indifférent : l'identifiant est une preuve, le titre une
    coïncidence à corroborer. Le chemin par titre n'est donc tenté que faute de
    mieux — c'est lui qui ramènerait un village pour la chanteuse Yoa.
    """
    if type_servi(reco) is None:
        return Resolution((), RAISON_TYPE_UNSUPPORTED)
    candidats: list[tuple[Entite, str]] = []
    try:
        for prop, valeur in identifiants_portes(reco).items():
            candidats += [(e, PREUVE_IDENTIFIANT)
                          for e in entites_par_identifiant(session, prop, valeur)]
        if not candidats:
            trouvees = entites_par_titres(session, [str(reco.get("title") or "")])
            candidats += [(e, PREUVE_TITRE) for e in trouvees.values()]
    except WikidataInjoignable as exc:
        if not candidats:
            return Resolution((), RAISON_HTTP_ERROR, detail=str(exc))
        log.warning("  recherche incomplète (%s) — on tranche sur ce qu'on a", exc)
    return verdict(reco, candidats)


@dataclass(frozen=True)
class Cas:
    """Le sort d'UNE reco, pour le rapport et pour le message de la chaîne."""

    reco_id: str
    titre: str
    raison: str
    preuve: str | None
    liens: int
    detail: str = ""


@dataclass
class RapportWikidata:
    """Agrégats d'une passe. `servies` porte le même sens que dans les autres
    passes (`enrich_tmdb.RapportTmdb`, `video_links_report.Report`) : la chaîne
    de venus les traite toutes de la même façon pour composer son message."""

    vues: int = 0
    ecrites: int = 0
    cas: list[Cas] = field(default_factory=list)

    @property
    def servies(self) -> set[str]:
        """Ids des recos pour lesquelles au moins un lien a été trouvé."""
        return {c.reco_id for c in self.cas if c.raison == RAISON_OK}

    @property
    def a_arbitrer(self) -> list[Cas]:
        return [c for c in self.cas if c.raison in RAISONS_A_ARBITRER]

    @property
    def liens_poses(self) -> int:
        return sum(c.liens for c in self.cas)


def appliquer(reco: dict[str, Any], liens: Sequence[Lien],
              *, timestamp: str | None = None) -> dict[str, Any]:
    """AJOUTE les liens à `reco["links"]` + l'audit trail, IN-PLACE.

    Un hôte déjà présent n'est jamais ajouté : garde-fou de dernier recours, la
    sélection l'ayant déjà écarté.
    """
    existants = list(reco.get("links") or [])
    hotes = {hote(str(e.get("url") or "")) for e in existants}
    ajouts = [lien.as_link() for lien in liens if hote(lien.url) not in hotes]
    if not ajouts:
        return reco
    return partial_update(reco, "links", existants + ajouts,
                          timestamp=timestamp or now_iso())


def run(*, root: Path, session: requests.Session | None = None,
        source: str | None = None, types: Sequence[str] | None = None,
        ids: Iterable[str] = (), limit: int | None = None,
        apply: bool = False, sleep: float = RATE_LIMIT_SLEEP) -> RapportWikidata:
    """Passe complète : sélectionne, résout, journalise, écrit si `apply`.

    `ids` restreint aux seules recos citées — ce dont la chaîne de venus a besoin
    pour ne traiter qu'un épisode fraîchement relu, sans rouvrir le corpus.
    """
    session = session or requests.Session()
    voulus = set(ids)
    filtre_types = set(types) if types else None
    rapport = RapportWikidata()
    resolues = 0

    for chemin in iter_reco_paths(root, source):
        try:
            reco = read_json(chemin)
        except (ValueError, OSError) as exc:
            log.warning("  %s illisible (%s) — ignoré", chemin.name, exc)
            rapport.cas.append(Cas(chemin.stem, "", RAISON_UNREADABLE, None, 0))
            continue
        reco_id = str(reco.get("id", chemin.stem))
        if voulus and reco_id not in voulus:
            continue
        if type_servi(reco) is None:
            continue
        if filtre_types and not (set(reco.get("types") or []) & filtre_types):
            continue
        rapport.vues += 1
        titre = str(reco.get("title") or "")

        if reco.get("status") != "validated":
            rapport.cas.append(Cas(reco_id, titre, RAISON_NOT_VALIDATED, None, 0))
            continue
        if limit is not None and resolues >= limit:
            continue

        resolution = resoudre(reco, session=session)
        resolues += 1
        rapport.cas.append(Cas(reco_id, titre, resolution.raison, resolution.preuve,
                               len(resolution.liens), resolution.detail))
        _journaliser(reco_id, titre, resolution)

        if resolution.liens and apply:
            try:
                appliquer(reco, resolution.liens)
            except EnrichedAtCorruptedError as exc:
                log.error("  %s · audit trail corrompu (%s) — non écrit", reco_id, exc)
                continue
            if write_json_if_changed(chemin, reco):
                rapport.ecrites += 1
        if sleep:
            time.sleep(sleep)

    return rapport


def _journaliser(reco_id: str, titre: str, resolution: Resolution) -> None:
    """Une ligne par reco : les liens trouvés, ou la raison du refus."""
    if resolution.liens:
        for lien in resolution.liens:
            log.info("  %s · %s → %s (%s, %s)", reco_id, titre[:34], lien.url,
                     lien.source, resolution.preuve)
        return
    detail = f" [{resolution.detail}]" if resolution.detail else ""
    log.info("  %s · %s → aucun lien : %s%s", reco_id, titre[:34],
             resolution.raison, detail)


def format_rapport(rapport: RapportWikidata) -> str:
    """Rendu texte : totaux, raisons, et ce qui reste à arbitrer."""
    raisons = Counter(c.raison for c in rapport.cas)
    total = (f"Recos vues : {rapport.vues} · liens trouvés : {rapport.liens_poses}"
             f" · recos écrites : {rapport.ecrites}")
    lignes = ["", total, "Refus / raisons :"]
    lignes += [f"  {raison:22} {n:5}" for raison, n in raisons.most_common()]
    if rapport.a_arbitrer:
        lignes.append(f"À arbitrer à la main : {len(rapport.a_arbitrer)}")
        lignes += [f"  • {c.reco_id} {c.titre[:32]} — {c.raison}"
                   f"{' [' + c.detail + ']' if c.detail else ''}"
                   for c in rapport.a_arbitrer]
    return "\n".join(lignes)
