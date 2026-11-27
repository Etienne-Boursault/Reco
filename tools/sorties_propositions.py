"""
sorties_propositions.py — une proposition de liens est-elle encore « en attente » ?

R4 B, 27/11/2026 ; tour 1 de revue de la PR #227. Tant qu'une PR de la relance attend, la
reco est sautée. Elle ne doit pas attendre pour toujours : une PR refermée sans fusion, ou
fusionnée par squash ou par rebase, laisse sa branche sur GitHub et son commit n'est jamais
ancêtre d'`origin/main`. Une proposition est donc **close** dès que :

1. ses adresses (celles de la dernière PR, `derniere`) figurent dans la reco d'`origin/main` :
   elle a été fusionnée, de n'importe quelle façon ;
2. sinon, avec `RECO_GITHUB_TOKEN`, la PR de la branche est fermée ou fusionnée selon l'API
   REST de GitHub (`GET /repos/{o}/{r}/pulls?head={o}:{branche}&state=all`, comme `ouvrir_pr`) ;
3. sinon (pas de jeton, API muette, aucune PR trouvée), l'ancienne règle de `sorties_plan` :
   branche absente du dépôt distant, ou commit ancêtre d'`origin/main`.

Une proposition close mais non fusionnée laisse la reco relançable ; elle ne reproduit que les
adresses nouvelles (l'état garde toutes celles déjà proposées). On ne teste que les propositions
des recos encore dans leur fenêtre : sinon le nombre d'appels grandirait sans fin.

L'appel HTTP est injecté (`lire`) ; sans lui, `_lire_api`.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import sorties_plan as sp
from branche_de_contenu import branche_distante_presente, est_ancetre_de_origin_main
from common import log
from publication import API_GITHUB, DELAI_API, Git, depot_github

Lire = Callable[[str, str], list[dict[str, Any]]]


def _lire_api(url: str, jeton: str) -> list[dict[str, Any]]:
    """GET de l'API REST, rend la liste JSON. Lève si l'API refuse ou ne répond pas."""
    requete = urllib.request.Request(  # noqa: S310 — URL construite ici, schéma https
        url, method="GET",
        headers={"Authorization": f"Bearer {jeton}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "reco-chaine-venus"})
    with urllib.request.urlopen(requete, timeout=DELAI_API) as reponse:  # noqa: S310
        return json.loads(reponse.read().decode("utf-8"))


def _pr_fermee(proprietaire: str, depot: str, branche: str, jeton: str, lire: Lire) -> bool | None:
    """La PR de la branche est-elle fermée (refermée ou fusionnée) ? None si l'API n'en voit aucune."""
    requete = urllib.parse.urlencode({"head": f"{proprietaire}:{branche}", "state": "all"})
    etats = [pr.get("state") for pr in lire(f"{API_GITHUB}/repos/{proprietaire}/{depot}/pulls?{requete}", jeton)]
    return None if not etats else "open" not in etats


def _close(racine: Path, cle: str, proposition: dict[str, Any], doc: dict[str, Any],
           depot_distant: tuple[str, str], jeton: str, lire: Lire) -> bool:
    propres = set(proposition.get("derniere") or proposition["adresses"])
    if propres and propres <= {lien["url"] for lien in doc.get("links") or []
                               if isinstance(lien, dict) and lien.get("url")}:
        return True
    proprietaire, depot = depot_distant
    if jeton and proprietaire:
        try:
            fermee = _pr_fermee(proprietaire, depot, proposition["branche"], jeton, lire)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.warning("état de la PR de %s illisible (%s) : règle de la branche", cle, type(exc).__name__)
        else:
            if fermee is not None:
                return fermee
    return not sp.proposition_en_attente(branche_distante_presente(racine, proposition["branche"]),
                                         est_ancetre_de_origin_main(racine, proposition["sha"]))


def propositions_en_attente(racine: Path, git: Git, etat: dict[str, Any],
                            recos: dict[str, tuple[str, dict[str, Any]]], jour: date, *,
                            jeton: str = "", lire: Lire | None = None) -> set[str]:
    """Les clés dont la PR attend encore : leurs recos sont sautées. Lève `ErreurGit` si git échoue."""
    a_tester = {cle: p for cle, p in etat["propositions"].items()
                if cle in recos and sp.en_fenetre(recos[cle][1], jour)}
    if not a_tester:
        return set()
    depot_distant = depot_github(git.url_distante()) if jeton else ("", "")
    return {cle for cle, p in a_tester.items()
            if not _close(racine, cle, p, recos[cle][1], depot_distant, jeton, lire or _lire_api)}
