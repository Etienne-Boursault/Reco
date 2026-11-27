"""Plan du jour de la relance des sorties annoncées : qui relancer, ce qu'on retient, ce qu'on dit.

Décision « R4 B », 27/11/2026 : la chaîne relance chaque jour, du jour de la sortie à J+30,
la recherche de liens des recos dont l'éditeur a noté `releaseDate`. Plan :
`_shared/docs/reco-v1/plans/pr-sorties-annoncees.md`, § 3 et remarques 5, 6, 8 et 12.

PUR : ni réseau, ni git, ni horloge. La date du jour, les recos, l'état et les faits de git
(reco présente sur `origin/main`, fichier modifié dans le clone, branche présente, commit
ancêtre) sont passés en paramètres par `sorties_annoncees.py`. Les fonctions de l'état
rendent un état neuf et ne modifient jamais leur argument ; la seule écriture sur disque
est `ecrire_etat` (`.tmp` puis `os.replace`), et la seule lecture `lire_etat`.

Règles qui ne se devinent pas :
- Une reco dont la PR attend (branche présente et commit pas encore ancêtre de
  `origin/main`) est sautée. Une PR refermée sans fusion ne reproduit jamais les mêmes
  adresses : l'état garde toutes celles déjà proposées (remarque 6).
- Une reco modifiée dans le clone est sautée, car sa PR ferait échouer le prochain
  `pull --ff-only` ; elle est signalée une seule fois par clé (remarque 12).
- Le signal ⏳ ne vaut que pour une reco relancée au moins une fois : une date vieille de
  deux ans, jamais relancée, ne dit rien (remarque 5).
- Un message ne se marque envoyé (`noter_signal`) qu'après son envoi : un envoi raté est
  retenté au passage suivant.
- Un état illisible arrête l'étape sans réécriture (famille F22) : `EtatIllisible`.
"""
from __future__ import annotations

import copy
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from common import atomic_write_text
from date_sortie import (
    DateSortieInvalide,
    analyser_date_sortie,
    dans_la_fenetre,
    fenetre_fermee,
    type_servi,
)


class EtatIllisible(Exception):
    """Le fichier d'état existe mais n'a pas la forme attendue : on ne le réécrit pas."""


@dataclass(frozen=True)
class PlanDuJour:
    a_relancer: list[dict[str, Any]]  # recos à chercher aujourd'hui
    modifiees: list[dict[str, Any]]   # sautées car modifiées dans le clone, pas encore signalées


def cle_de(doc: dict[str, Any]) -> str:
    return f"{doc.get('sourceId', '')}/{doc.get('id', '')}"


def _sortie(doc: dict[str, Any]) -> date | None:
    """La date de sortie d'une reco relançable (validée, type servi, date valide), sinon None."""
    if doc.get("status") != "validated" or not type_servi(doc.get("types") or []):
        return None
    try:
        return analyser_date_sortie(doc.get("releaseDate"))
    except DateSortieInvalide:
        return None


def proposition_en_attente(branche_existe: bool, commit_ancetre: bool) -> bool:
    """Vrai tant que la branche existe sur GitHub et que son commit n'est pas dans `origin/main`."""
    return branche_existe and not commit_ancetre


def plan_du_jour(recos: Iterable[dict[str, Any]], aujourdhui: date, etat: dict[str, Any], *,
                 sur_origin: set[str], modifiees: set[str], en_attente: set[str]) -> PlanDuJour:
    """Les recos à relancer, et celles à signaler « modifiée, sautée » (une fois par clé).

    `sur_origin`, `modifiees` et `en_attente` sont des ensembles de clés (`cle_de`).
    """
    a_relancer: list[dict[str, Any]] = []
    sautees: list[dict[str, Any]] = []
    for doc in recos:
        sortie = _sortie(doc)
        cle = cle_de(doc)
        if sortie is None or not dans_la_fenetre(sortie, aujourdhui) or cle not in sur_origin:
            continue
        if cle in modifiees:
            if not deja_signale(etat, "sautee", cle):
                sautees.append(doc)
        elif cle not in en_attente:
            a_relancer.append(doc)
    return PlanDuJour(a_relancer, sautees)


def sabliers(recos: Iterable[dict[str, Any]], aujourdhui: date,
             etat: dict[str, Any]) -> list[dict[str, Any]]:
    """Recos relancées au moins une fois, sans lien posé, dont la fenêtre est fermée, pas encore signalées."""
    resultat = []
    for doc in recos:
        cle = cle_de(doc)
        sortie = _sortie(doc)
        if (sortie is not None and fenetre_fermee(sortie, aujourdhui)
                and cle in etat["relancees"] and cle not in etat["propositions"]
                and not deja_signale(etat, "sablier", cle)):
            resultat.append(doc)
    return resultat


# --- l'état -----------------------------------------------------------------------

def etat_vide() -> dict[str, Any]:
    """`dernier_jour` : AAAA-MM-JJ du dernier passage ; `propositions` : clé -> {branche, sha,
    adresses} (adresses cumulées, jamais retirées) ; `relancees` : clés cherchées au moins une
    fois ; `signaux` : « genre:clé » déjà envoyés ; `erreurs` : clé -> dernière panne."""
    return {"dernier_jour": None, "propositions": {}, "relancees": [], "signaux": [], "erreurs": {}}


def _forme_ok(etat: dict[str, Any]) -> bool:
    if not (etat["dernier_jour"] is None or isinstance(etat["dernier_jour"], str)):
        return False
    if not (isinstance(etat["relancees"], list) and isinstance(etat["signaux"], list)
            and isinstance(etat["erreurs"], dict) and isinstance(etat["propositions"], dict)):
        return False
    return all(
        isinstance(p, dict) and isinstance(p.get("branche"), str) and isinstance(p.get("sha"), str)
        and isinstance(p.get("adresses"), list)
        for p in etat["propositions"].values())


def lire_etat(chemin: Path) -> dict[str, Any]:
    """Un fichier absent donne l'état vide ; un fichier de forme fausse lève `EtatIllisible`."""
    try:
        brut = json.loads(chemin.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return etat_vide()
    except (OSError, ValueError) as exc:  # JSON faux, UTF-8 faux, lecture refusée
        raise EtatIllisible(f"{chemin} : {exc}") from exc
    if not isinstance(brut, dict):
        raise EtatIllisible(f"{chemin} : un objet JSON était attendu")
    etat = {**etat_vide(), **brut}
    if not _forme_ok(etat):
        raise EtatIllisible(f"{chemin} : forme inattendue")
    return etat


def ecrire_etat(chemin: Path, etat: dict[str, Any]) -> None:
    """Écrit l'état en JSON lisible : `.tmp` puis `os.replace`, jamais de fichier tronqué."""
    atomic_write_text(chemin, json.dumps(etat, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def noter_jour(etat: dict[str, Any], aujourdhui: date) -> dict[str, Any]:
    neuf = copy.deepcopy(etat)
    neuf["dernier_jour"] = aujourdhui.isoformat()
    return neuf


def jour_deja_traite(etat: dict[str, Any], aujourdhui: date) -> bool:
    return etat["dernier_jour"] == aujourdhui.isoformat()


def noter_relance(etat: dict[str, Any], cles: Iterable[str]) -> dict[str, Any]:
    neuf = copy.deepcopy(etat)
    neuf["relancees"] = sorted(set(neuf["relancees"]) | set(cles))
    return neuf


def noter_proposition(etat: dict[str, Any], cle: str, branche: str, sha: str,
                      adresses: Iterable[str]) -> dict[str, Any]:
    """Note la branche et le commit de la dernière PR, et cumule les adresses proposées."""
    neuf = copy.deepcopy(etat)
    anciennes = neuf["propositions"].get(cle, {}).get("adresses", [])
    cumul = anciennes + [a for a in adresses if a not in anciennes]
    neuf["propositions"][cle] = {"branche": branche, "sha": sha, "adresses": cumul}
    return neuf


def adresses_nouvelles(etat: dict[str, Any], cle: str, adresses: Iterable[str]) -> list[str]:
    """Les adresses trouvées qui n'ont encore jamais été proposées pour cette reco."""
    vues = etat["propositions"].get(cle, {}).get("adresses", [])
    return [a for a in adresses if a not in vues]


def deja_signale(etat: dict[str, Any], genre: str, cle: str) -> bool:
    return f"{genre}:{cle}" in etat["signaux"]


def noter_signal(etat: dict[str, Any], genre: str, cle: str) -> dict[str, Any]:
    neuf = copy.deepcopy(etat)
    if not deja_signale(neuf, genre, cle):
        neuf["signaux"].append(f"{genre}:{cle}")
    return neuf


def noter_erreur(etat: dict[str, Any], cle: str, message: str) -> tuple[dict[str, Any], bool]:
    """Note la panne ; le booléen dit si c'est la première pour cette clé (donc à signaler)."""
    neuf = copy.deepcopy(etat)
    premiere = cle not in neuf["erreurs"]
    neuf["erreurs"][cle] = message
    return neuf, premiere


def effacer_erreur(etat: dict[str, Any], cle: str) -> dict[str, Any]:
    neuf = copy.deepcopy(etat)
    neuf["erreurs"].pop(cle, None)
    return neuf


# --- les messages Matrix ---------------------------------------------------------------

def _jj_mm(doc: dict[str, Any]) -> str:
    return analyser_date_sortie(doc["releaseDate"]).strftime("%d/%m")


def message_trouvaille(doc: dict[str, Any], labels: list[str], lien_pr: str) -> str:
    n = len(labels)
    trouves = "1 lien trouvé" if n == 1 else f"{n} liens trouvés"
    return (f"🗓️ « {doc['title']} » : {trouves} après sa sortie du {_jj_mm(doc)} "
            f"({', '.join(labels)}). À relire : {lien_pr}\n"
            "La PR ne change que la reco : l'œuvre et les recos sœurs ne suivent pas, et il reste "
            "à ajouter l'œuvre aux playlists de l'épisode.")


def message_sablier(doc: dict[str, Any]) -> str:
    return (f"⏳ « {doc['title']} » : sortie annoncée le {_jj_mm(doc)}, aucun lien trouvé en "
            "30 jours. La relance s'arrête ; les liens se posent à la main si besoin.")


def message_modifiee(doc: dict[str, Any]) -> str:
    return (f"⚠️ « {doc['title']} » : reco modifiée, sautée. Sa PR de liens ferait échouer le "
            "prochain pull de la chaîne ; la relance reprend quand la modification est publiée.")


def message_panne(cle: str, message: str) -> str:
    return f"⚠️ Relance des sorties annoncées, {cle} : {message}"
