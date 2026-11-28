"""bord_systeme.py — coûts, modèles et image de la chaîne pour le tableau de bord.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 2 lignes « Coûts », « Modèles » et « Santé : image », tranche 3b,
relecture R20 : « inconnu » au lieu de 0 $).

Tout se lit sur le disque local, sans réseau : la base de télémétrie (en `mode=ro`, jamais créée),
le `compose.yml` du clone et l'environnement du processus. Le serveur de relecture n'a qu'un fil :
deux requêtes bornées par le temps, pas de balayage, et aucune exception ne sort de `lire()`.

CHAQUE CHAMP SE LIT SEUL (F22, F12)
-----------------------------------
Une base absente, verrouillée ou illisible, un coût mal formé, un `compose.yml` sans ligne `image:`
rendent `None` pour ce champ : « inconnu », jamais 0 $ ni « aucun ». Les autres champs restent lus.
Une semaine sans aucun appel est en revanche mesurée : `appels: 0`.

LES COÛTS
---------
Deux fenêtres glissantes de 7 jours à partir de `maintenant` (`semaine` : les 7 derniers jours,
`precedente` : les 7 d'avant), sur `llm_calls.recorded_at`, pour la source donnée (jointure sur
`stage_attempts.source_id`). `telemetry.reports.couts()` additionne par devise ; un appel sans
coût connu est compté à part (`unknownCostCalls`) et ne vaut jamais 0 $. Un coût sans devise est
traité comme inconnu (sinon `couts()` le rangerait sous la clé `None`). Quand `known` est `None`,
rien n'est connu ; quand `known` existe avec `unknownCostCalls > 0`, c'est un minimum.

LES MODÈLES
-----------
`extraction` : le modèle de la dernière extraction réussie (`stage_attempts.model`), source
`mesure`. À défaut, `modeles_llm.modele_extraction()`, source `env` : c'est l'environnement du
processus de relecture, tel qu'il était au démarrage du conteneur (« .env au démarrage »), pas
forcément celui de la chaîne. `secours` : toujours `env`, car aucun modèle de secours n'est
enregistré tant qu'il n'a pas servi ; `nom: None` veut dire « secours coupé » (valeur `aucun`).

L'IMAGE
-------
La ligne `image:` de `deploy/venus/compose.yml` du clone : ce que le fichier demande, pas ce qui
tourne (le conteneur ne voit pas son propre démarrage).
"""
from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import common
import modeles_llm
from telemetry.recorder import default_db_path
from telemetry.reports import couts

SEMAINE = timedelta(days=7)
_IMAGE = re.compile(r"^\s*image:\s*([^\s#]+)", re.MULTILINE)
#: Ce qu'une lecture rend quand elle échoue : on l'attrape, on la journalise, le champ est inconnu.
_ERREURS = (sqlite3.Error, ArithmeticError, ValueError, TypeError, OSError)


def _ouvrir(db_path: Path) -> sqlite3.Connection | None:
    """La base en lecture seule, ou `None` si elle n'existe pas (jamais créée par la page)."""
    if not db_path.exists():
        return None
    return sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=1)


def _instant(date: datetime) -> str:
    """Même forme que `recorded_at` : UTC, millisecondes, `+00:00` (la comparaison est textuelle)."""
    return date.astimezone(UTC).isoformat(timespec="milliseconds")


def _fenetre(appels: list[dict[str, Any]]) -> dict[str, Any]:
    par_modele: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for appel in appels:
        par_modele[appel["model"]].append(appel)
    return {"appels": len(appels), "cout": couts(appels),
            "par_modele": {m: couts(liste) for m, liste in sorted(par_modele.items())}}


def _lire_couts(db_path: Path, source_id: str, maintenant: datetime
                ) -> dict[str, dict[str, Any] | None]:
    inconnus: dict[str, dict[str, Any] | None] = {"semaine": None, "precedente": None}
    try:
        conn = _ouvrir(db_path)
        if conn is None:
            return inconnus
        try:
            lignes = conn.execute(
                "SELECT c.model, c.cost_decimal, c.cost_currency, c.recorded_at FROM llm_calls c "
                "JOIN stage_attempts s ON s.id = c.stage_attempt_id "
                "WHERE s.source_id = ? AND c.recorded_at >= ?",
                [source_id, _instant(maintenant - 2 * SEMAINE)]).fetchall()
        finally:
            conn.close()
        limite = _instant(maintenant - SEMAINE)
        semaines: dict[bool, list[dict[str, Any]]] = {True: [], False: []}
        for modele, cout, devise, quand in lignes:
            # Un coût sans devise ne vaut rien : `couts()` le rangerait sous la clé `None`.
            semaines[quand >= limite].append({"model": modele, "cost_currency": devise,
                                              "cost_decimal": cout if devise else None})
        return {"semaine": _fenetre(semaines[True]), "precedente": _fenetre(semaines[False])}
    except _ERREURS as exc:
        common.log.warning("bord_systeme : coûts illisibles (%s) : %s", db_path, exc)
        return inconnus


def _modele_mesure(db_path: Path, source_id: str) -> tuple[str, str] | None:
    """(modèle, fin) de la dernière extraction réussie qui a nommé son modèle, sinon `None`."""
    try:
        conn = _ouvrir(db_path)
        if conn is None:
            return None
        try:
            ligne = conn.execute(
                "SELECT model, ended_at FROM stage_attempts WHERE source_id = ? "
                "AND stage = 'extract' AND status = 'succeeded' AND ended_at IS NOT NULL "
                "AND model IS NOT NULL AND model != '' ORDER BY ended_at DESC LIMIT 1",
                [source_id]).fetchone()
        finally:
            conn.close()
    except _ERREURS as exc:
        common.log.warning("bord_systeme : modèle mesuré illisible (%s) : %s", db_path, exc)
        return None
    return (ligne[0], ligne[1]) if ligne else None


def _lire_modeles(db_path: Path, source_id: str) -> dict[str, dict[str, Any]]:
    mesure = _modele_mesure(db_path, source_id)
    extraction = ({"nom": mesure[0], "source": "mesure", "date": mesure[1]} if mesure else
                  {"nom": modeles_llm.modele_extraction(), "source": "env", "date": None})
    return {"extraction": extraction,
            "secours": {"nom": modeles_llm.modele_secours(), "source": "env"}}


def _lire_image() -> str | None:
    chemin = common.TOOLS_DIR.parent / "deploy" / "venus" / "compose.yml"
    try:
        trouve = _IMAGE.search(chemin.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        common.log.warning("bord_systeme : compose.yml illisible (%s) : %s", chemin, exc)
        return None
    return trouve.group(1) if trouve else None


def lire(source_id: str, *, maintenant: datetime | None = None) -> dict[str, Any]:
    """Le bloc « coûts, modèles, image » : ne lève jamais, chaque champ illisible vaut `None`.

    {"couts": {"semaine": FENETRE | None, "precedente": FENETRE | None},
     "modeles": {"extraction": {"nom", "source": "mesure" | "env", "date": iso | None},
                 "secours": {"nom": str | None, "source": "env"}},
     "image": "reco-atelier:…" | None}
    FENETRE = {"appels": int, "cout": couts(), "par_modele": {modèle: couts()}}
    """
    db_path = default_db_path()
    return {"couts": _lire_couts(db_path, source_id, maintenant or datetime.now(UTC)),
            "modeles": _lire_modeles(db_path, source_id), "image": _lire_image()}
