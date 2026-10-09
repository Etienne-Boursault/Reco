"""La boucle commune aux passes de liens ajoutées le 2026-10-10.

Plateformes vidéo, jeux sans studio, YouTube Music : trois passes qui ne
diffèrent que par ce qu'elles savent résoudre. Recopier trois fois la sélection,
le journal et l'écriture aurait fait trois endroits où oublier le statut
`validated` ou l'audit trail — d'où ce module, et rien d'autre.

Le rapport et le sort d'une reco sont ceux de `wikidata_links` (`Cas`,
`RapportWikidata`) : la chaîne de venus lit `servies` de la même façon pour
toutes ses passes, et un second type de rapport n'aurait rien dit de plus.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from common import log, read_json, write_json_if_changed
from enrich_creators import iter_reco_paths
from enrichment.field_refresher import EnrichedAtCorruptedError, partial_update
from enrichment.tracker import now_iso
from wikidata_links import Cas, RapportWikidata, _journaliser
from wikidata_matching import (
    RAISON_NOT_VALIDATED,
    RAISON_UNREADABLE,
    Lien,
    Resolution,
    hote,
)

Resoudre = Callable[[dict[str, Any]], Resolution]
#: Où placer un lien neuf dans la liste existante (index d'insertion).
Placer = Callable[[list[dict[str, Any]], Lien], int]


def a_la_fin(liens: list[dict[str, Any]], _lien: Lien) -> int:
    """Placement par défaut : à la suite de ce qui est déjà posé."""
    return len(liens)


def appliquer(reco: dict[str, Any], liens: Sequence[Lien], *,
              placer: Placer = a_la_fin, timestamp: str | None = None) -> dict[str, Any]:
    """AJOUTE les liens à `reco["links"]` + l'audit trail, IN-PLACE.

    Un hôte déjà présent n'est jamais ajouté (même garde-fou que
    `wikidata_links.appliquer`) : jamais deux liens Netflix, jamais un lien posé
    à la main remplacé par celui d'une passe.
    """
    existants = list(reco.get("links") or [])
    hotes = {hote(str(e.get("url") or "")) for e in existants}
    ajoutes = 0
    for lien in liens:
        if hote(lien.url) in hotes:
            continue
        existants.insert(placer(existants, lien), lien.as_link())
        hotes.add(hote(lien.url))
        ajoutes += 1
    if not ajoutes:
        return reco
    return partial_update(reco, "links", existants, timestamp=timestamp or now_iso())


def derouler(*, root: Path, source: str | None, ids: Iterable[str],
             servie: Callable[[dict[str, Any]], bool], resoudre: Resoudre,
             apply: bool, placer: Placer = a_la_fin,
             sleep: float = 0.0) -> RapportWikidata:
    """Sélectionne, résout, journalise, écrit si `apply`.

    `servie` dit si la passe sait traiter la reco (type, champs requis) ; une
    reco qu'elle ne sait pas traiter n'apparaît pas au rapport. `ids` restreint
    aux recos d'un épisode, comme pour les autres passes de la chaîne.
    """
    voulus = set(ids)
    rapport = RapportWikidata()
    for chemin in iter_reco_paths(root, source):
        try:
            reco = read_json(chemin)
        except (ValueError, OSError) as exc:
            log.warning("  %s illisible (%s) — ignoré", chemin.name, exc)
            rapport.cas.append(Cas(chemin.stem, "", RAISON_UNREADABLE, None, 0))
            continue
        reco_id = str(reco.get("id", chemin.stem))
        if (voulus and reco_id not in voulus) or not servie(reco):
            continue
        rapport.vues += 1
        titre = str(reco.get("title") or "")
        if reco.get("status") != "validated":
            rapport.cas.append(Cas(reco_id, titre, RAISON_NOT_VALIDATED, None, 0))
            continue

        resolution = resoudre(reco)
        rapport.cas.append(Cas(reco_id, titre, resolution.raison, resolution.preuve,
                               len(resolution.liens), resolution.detail))
        _journaliser(reco_id, titre, resolution)
        if resolution.liens and apply:
            avant = len(reco.get("links") or [])
            try:
                appliquer(reco, resolution.liens, placer=placer)
            except EnrichedAtCorruptedError as exc:
                log.error("  %s · audit trail corrompu (%s) — non écrit", reco_id, exc)
                continue
            # Rien d'ajouté, rien d'écrit : réécrire le fichier ne ferait que
            # changer sa mise en forme.
            if len(reco.get("links") or []) != avant and write_json_if_changed(chemin, reco):
                rapport.ecrites += 1
        if sleep:
            time.sleep(sleep)
    return rapport
