"""bord_github.py — les données GitHub du tableau de bord : PR, CI et déploiement.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 2 lignes « Publication » et « Santé », tranche 3a, relectures R3, R4, R7).

Quatre appels à l'API publique de GitHub, du dépôt d'origine du clone (`git remote`) :
  - les PR ouvertes, et les PR fermées d'où l'on garde celles qui ont une `merged_at` ;
  - la dernière CI de `main` (`ci.yml`) et le dernier déploiement (`deploy.yml`).

CE QUI VIENT DE `bord_distant`
------------------------------
Rien n'est recopié : le cache `distant.json` (clé `github`, à côté de `audience`), le
verrou `distant.lock`, la fraîcheur de 10 min (succès comme échec, F6), le processus
détaché et son `distant.log` (F24), la lecture bornée en taille et en durée, et l'ouvreur
qui refuse toute redirection. Un 3xx compte donc comme une panne, et la réponse doit venir
exactement de `api.github.com`. Ce module n'ajoute que les appels et leur lecture.
La page ne lit que le cache : `lire()` ne touche ni le réseau ni git.

LES PR : SEULES CELLES DU DÉPÔT
-------------------------------
Une PR d'un fork peut s'appeler `contenu/x` sans venir de la chaîne : on ne garde que
`head.repo.full_name` égal au dépôt (R4). Les PR d'épisode (`contenu/<guid>`) sont séparées des
sorties annoncées (`contenu/sorties-…`, R3). Les autres branches ne sont pas du tableau de bord.
Les PR fusionnées viennent des 30 PR fermées les plus récemment modifiées (« publié » se lit sur
`merged_at`, R7 ; les 100 d'avant pesaient 1,9 Mo pour une limite de 2 Mo, mesuré le 28/11/2026,
tour 1, E1). Cette fenêtre glisse, mais la liste gardée est cumulative (tour 2, F-a, 28/11/2026) :
chaque lecture réussie y ajoute les PR lues à celles du cache, par branche, avec la date de fusion la
plus récente, et garde les 200 plus récentes. Une PR fusionnée le reste, donc une panne de l'appel
des fermées garde la liste d'avant (et se note dans `pannes`). Les autres blocs sont des instantanés.
Les PR ouvertes portent `coupee: true` si la page de l'API était pleine (F23).

Toute branche `contenu/*` hors `sorties-` est rangée dans `episodes`, car ce module ne lit pas le
corpus : il ne sait pas quels slugs sont des guids d'épisode. Des PR faites à la main
(`contenu/liens-rebelle`) s'y trouvent donc aussi (tour 1, F2). Chaque PR garde sa `branche` : c'est à
l'appelant, qui connaît les guids, de la rapprocher de `slugify(guid)` (`publication.py`).

LE JETON
--------
`RECO_GITHUB_TOKEN`, s'il existe, ne sert qu'aux appels des PR (plus de requêtes par heure) ; un
401 (jeton expiré) répète l'appel sans jeton, le dépôt étant public, et note `jeton: "refuse"` (F3) ; les
appels des Actions restent anonymes : le dépôt est public, et un jeton à grain fin sans droit sur
les Actions risquerait un 403 (note du plan, § 2). Il ne passe jamais dans l'adresse, et il
n'est ni dans un journal, ni dans un message, ni dans le cache (F15) : les erreurs ne sont
décrites que par leur type ou leur code HTTP. Une limite de débit atteinte (403 ou 429 avec
`X-RateLimit-Remaining: 0` ou `Retry-After`) donne l'état `limite`.

LES FORMES INATTENDUES (F6, F12)
--------------------------------
Chaque bloc se lit seul : une forme inattendue dans l'un le rend `None` (inconnu, jamais
« aucune PR » ni « CI verte »), et les autres restent. Chaque appel est isolé de même (E1) : un appel
en panne met son seul bloc à `None` et se note dans `pannes` (bloc, état, détail). L'état de la
source reste `ok` si un appel au moins a réussi ; si tous échouent, la panne garde en revanche
les dernières données entières, avec leur heure (`lu`).
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import bord_distant as bd
import common
from common import log
from publication import API_GITHUB, Git, depot_github

SOURCE = "github"
VARIABLE_JETON = "RECO_GITHUB_TOKEN"
_HOTE = urlsplit(API_GITHUB).hostname
_PAGE = 100
_PAGE_FERMEES = 30
_TITRE_MAX = 200
#: Les PR fusionnées gardées d'une lecture à l'autre (tour 2, F-a).
_FUSIONNEES_MAX = 200
LIBELLES = {"ok": "à jour", "inconnu": "inconnu", "panne": "panne",
            "limite": "limite de débit atteinte", "reponse-illisible": "réponse illisible",
            "cache-illisible": "cache illisible"}


class _Echec(Exception):
    """Un appel raté : l'état du cache et son détail, sans secret."""

    def __init__(self, etat: str, detail: str) -> None:
        super().__init__(detail)
        self.etat, self.detail = etat, detail


def _depot() -> str:
    """`proprietaire/depot` de l'origine du clone ; vide si ce n'est pas GitHub."""
    proprietaire, depot = depot_github(Git(common.PROJECT_ROOT).url_distante())
    return f"{proprietaire}/{depot}" if proprietaire else ""


def _get(url: str, jeton: str | None) -> Any:
    """Le JSON de `url` ; `_Echec` sinon. Le jeton n'est que dans l'en-tête."""
    en_tetes = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "reco-bord"}
    if jeton:
        en_tetes["Authorization"] = f"Bearer {jeton}"
    requete = urllib.request.Request(url, headers=en_tetes)  # noqa: S310 — https://api.github.com
    try:
        with bd._ouvreur().open(requete, timeout=bd._DELAI) as reponse:
            if urlsplit(reponse.geturl()).hostname != _HOTE:
                raise _Echec("panne", "autre hôte")
            corps = bd._lire_borne(reponse)
    except urllib.error.HTTPError as exc:
        exc.close()
        limite = exc.code in (403, 429) and (exc.headers.get("X-RateLimit-Remaining") == "0"
                                             or exc.code == 429 or "Retry-After" in exc.headers)
        raise _Echec("limite" if limite else "panne", f"HTTP {exc.code}") from None
    except (OSError, http.client.HTTPException) as exc:
        raise _Echec("panne", type(exc).__name__) from None
    if len(corps) > bd._TAILLE_MAX:
        raise _Echec("reponse-illisible", "trop longue")
    try:
        return json.loads(corps)
    except ValueError:
        raise _Echec("reponse-illisible", "JSON invalide") from None


def _groupe(branche: str) -> str | None:
    if branche.startswith("contenu/sorties-"):
        return "sorties"
    return "episodes" if branche.startswith("contenu/") else None


def _pr(brut: Any, depot: str, cle_date: str) -> dict[str, Any] | None:
    """Une PR du dépôt sur une branche de contenu ; `None` pour toute autre ; `ValueError` si illisible."""
    if not isinstance(brut, dict) or not isinstance(brut.get("head"), dict):
        raise ValueError("PR de forme inattendue")
    tete = brut["head"]
    origine = tete.get("repo")                       # `None` : fork supprimé
    if origine is not None and not isinstance(origine, dict):
        raise ValueError("PR de forme inattendue")
    if origine is None or str(origine.get("full_name")).lower() != depot.lower():
        return None
    if cle_date == "merged_at" and brut.get(cle_date) is None:
        return None                                   # fermée sans fusion
    numero, titre, branche, date = brut.get("number"), brut.get("title"), tete.get("ref"), \
        brut.get(cle_date)
    if type(numero) is not int or not isinstance(titre, str) or not isinstance(branche, str):
        raise ValueError("PR de forme inattendue")
    bd._date(date)                                   # `ValueError` si absente ou sans fuseau
    groupe = _groupe(branche)
    if groupe is None:
        return None
    return {"numero": numero, "titre": titre[:_TITRE_MAX], "branche": branche, "groupe": groupe,
            "date": date, "adresse": f"https://github.com/{depot}/pull/{numero}"}


def _liste(reponse: Any, depot: str, cle_date: str) -> list[dict[str, Any]]:
    """Les PR gardées, les plus récentes d'abord (F23 : un ordre voulu, pas celui de l'API)."""
    if not isinstance(reponse, list):
        raise ValueError("liste attendue")
    gardees = [pr for pr in (_pr(brut, depot, cle_date) for brut in reponse) if pr]
    return sorted(gardees, key=lambda pr: bd._date(pr["date"]), reverse=True)


def _ouvertes(reponse: Any, depot: str) -> dict[str, Any]:
    prs = _liste(reponse, depot, "created_at")
    return {"episodes": [p for p in prs if p["groupe"] == "episodes"],
            "sorties": [p for p in prs if p["groupe"] == "sorties"],
            "coupee": len(reponse) >= _PAGE}


def _fusionnees(reponse: Any, depot: str) -> list[dict[str, Any]]:
    return _liste(reponse, depot, "merged_at")


def _execution(reponse: Any, depot: str) -> dict[str, Any] | None:
    """La dernière exécution terminée : conclusion, date, adresse ; `None` s'il n'y en a pas."""
    courses = reponse.get("workflow_runs") if isinstance(reponse, dict) else None
    if not isinstance(courses, list):
        raise ValueError("liste d'exécutions attendue")
    if not courses:
        return None
    # Tour 1, F5 : `deploy.yml` suit `workflow_run`, il est sauté (`skipped`) quand la CI échoue. La
    # requête ne garde que les exécutions terminées ; on prend la première qui a un vrai résultat,
    # sinon la plus récente. Revue globale, D10 : `ci.yml` annule l'exécution en cours quand une
    # nouvelle démarre, « annulée » n'est donc pas un résultat non plus.
    course = next((c for c in courses if isinstance(c, dict)
                   and c.get("conclusion") not in (None, "skipped", "cancelled")), courses[0])
    if not isinstance(course, dict):
        raise ValueError("exécution de forme inattendue")
    ident, conclusion, date = course.get("id"), course.get("conclusion"), course.get("updated_at")
    if type(ident) is not int or not isinstance(conclusion, str):
        raise ValueError("exécution de forme inattendue")
    bd._date(date)
    return {"conclusion": conclusion[:40], "date": date,
            "adresse": f"https://github.com/{depot}/actions/runs/{ident}"}


def _bloc(fabrique: Any, brut: Any, depot: str) -> Any:
    """Un bloc seul : une forme inattendue le rend `None` (inconnu), sans toucher aux autres."""
    try:
        return fabrique(brut, depot)
    except ValueError as exc:
        log.warning("bord : github, %s illisible (%s)", fabrique.__name__.strip("_"), exc)
        return None


def _cumuler(donnees: dict[str, Any], avant: dict[str, Any] | None) -> dict[str, Any]:
    """Les PR fusionnées lues réunies à celles du cache, par branche, les 200 plus récentes (F-a).

    Un bloc `fusionnees` à `None` (panne) garde celui d'avant ; sans liste d'avant, il reste `None`.
    Une entrée abîmée du cache est laissée de côté, jamais recopiée.
    """
    anciennes = (avant or {}).get("fusionnees")
    nouvelles = donnees["fusionnees"]
    if nouvelles is None and not isinstance(anciennes, list):
        return donnees
    par_branche: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for pr in [*(anciennes if isinstance(anciennes, list) else []), *(nouvelles or [])]:
        try:
            branche, quand = pr["branche"], bd._date(pr["date"])
            if branche not in par_branche or quand >= par_branche[branche][0]:
                par_branche[branche] = (quand, pr)
        except (KeyError, TypeError, ValueError):
            log.warning("bord : github, une PR fusionnée du cache est illisible, laissée de côté")
    recentes = sorted(par_branche.values(), key=lambda t: t[0], reverse=True)[:_FUSIONNEES_MAX]
    return {**donnees, "fusionnees": [pr for _, pr in recentes]}


def _appeler() -> tuple[str, str | None, dict[str, Any] | None]:
    """Les quatre appels, chacun isolé : (état, détail sans secret, données ou None)."""
    depot = _depot()
    if not depot:
        return "panne", "dépôt inconnu", None
    jeton = os.environ.get(VARIABLE_JETON)
    base = f"{API_GITHUB}/repos/{depot}"
    ouv = f"{base}/pulls?state=open&per_page={_PAGE}"
    fer = f"{base}/pulls?state=closed&sort=updated&direction=desc&per_page={_PAGE_FERMEES}"
    ci = f"{base}/actions/workflows/ci.yml/runs?branch=main&event=push&status=completed&per_page=10"
    dep = f"{base}/actions/workflows/deploy.yml/runs?branch=main&status=completed&per_page=10"
    appels = (  # (bloc, adresse, avec jeton, lecture) ; le jeton ne sert qu'aux PR
        ("ouvertes", ouv, True, _ouvertes), ("fusionnees", fer, True, _fusionnees),
        ("ci", ci, False, _execution), ("deploiement", dep, False, _execution))
    donnees: dict[str, Any] = {"depot": depot, "pannes": {}, "jeton": None}
    for bloc, adresse, avec_jeton, fabrique in appels:
        try:
            try:
                brut = _get(adresse, jeton if avec_jeton else None)
            except _Echec as exc:
                if not (avec_jeton and jeton and exc.detail == "HTTP 401"):
                    raise
                jeton, donnees["jeton"] = None, "refuse"      # F3 : le dépôt est public
                brut = _get(adresse, None)
        except _Echec as exc:
            donnees[bloc] = None
            donnees["pannes"][bloc] = {"etat": exc.etat, "detail": exc.detail}
            continue
        donnees[bloc] = _bloc(fabrique, brut, depot)
    pannes = donnees["pannes"]
    if len(pannes) == len(appels):
        premiere = next(iter(pannes.values()))
        return premiere["etat"], premiere["detail"], None
    return "ok", None, donnees


def rafraichir(*, maintenant: datetime | None = None) -> str:
    """Relit GitHub si le cache est périmé, sous le verrou de `bord_distant`."""
    return bd.rafraichir_source(SOURCE, _appeler, maintenant=maintenant, cumuler=_cumuler)


def lire(*, maintenant: datetime | None = None, relancer: bool = True) -> dict[str, Any]:
    """L'état de GitHub pour la page, sans jamais toucher le réseau ni git.

    `{"source", "etat", "libelle", "detail", "donnees", "lu", "essai", "age", "relance"}`, comme
    `bord_distant.lire`. `etat` : `ok`, `inconnu` (aucun cache, ou un état que l'on ne connaît
    pas), `panne`, `limite`, `reponse-illisible` ou `cache-illisible` ; il dit le dernier essai, et
    `donnees` reste celles d'avant une panne (`lu`, `age`). `donnees` :
    `{"depot", "ouvertes": {"episodes": [PR], "sorties": [PR], "coupee"} | None,
    "fusionnees": [PR] | None (cumulative, 200 au plus), "ci": course | None, "deploiement": course | None,
    "pannes": {bloc: {"etat", "detail"}}, "jeton": "refuse" | None}` ;
    PR = `{"numero", "titre", "branche", "groupe", "date", "adresse"}` ;
    course = `{"conclusion", "date", "adresse"}`. Un bloc `None` est inconnu.
    """
    maintenant = maintenant or datetime.now(UTC)
    try:
        entree = bd._lire_cache(SOURCE).get(SOURCE)
    except bd.CacheIllisible as exc:
        log.warning("bord : %s", exc)
        entree, etat = None, "cache-illisible"
    else:
        etat = (entree or {}).get("etat", "inconnu")
        if etat not in LIBELLES:
            etat = "inconnu"
    entree = entree or {}
    relance = (relancer and etat != "cache-illisible" and bd._perime(entree or None, maintenant)
               and bd._lancer(Path(__file__).resolve(), SOURCE))
    lu = entree.get("lu")
    return {"source": SOURCE, "etat": etat, "libelle": LIBELLES[etat],
            "detail": entree.get("detail"), "donnees": entree.get("donnees"), "lu": lu,
            "essai": entree.get("essai"),
            "age": int((maintenant - bd._date(lu)).total_seconds()) if lu else None,
            "relance": relance}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lecture de GitHub pour le tableau de bord.")
    parser.add_argument("commande", choices=["rafraichir"])
    parser.parse_args(argv)
    print(f"{SOURCE} : {rafraichir()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
