#!/usr/bin/env python3
"""Vérifie la couverture Python métrique par métrique.

POURQUOI CE SCRIPT EXISTE — ne le supprimez pas en le prenant pour une
redondance avec `--cov-fail-under`.

`--cov-fail-under` de coverage.py porte sur un TOTAL COMBINÉ lignes+branches
(`totals.percent_covered`). Autrement dit, ceci passe un seuil de 95 % :

    lignes    99,0 %   (9900/10000)
    branches  91,0 %   ( 3640/4000)   <-- très en dessous
    combiné   96,7 %   -> --cov-fail-under=95 : OK

L'exigence du projet est ≥95 % sur CHAQUE métrique. Il faut donc lire le
rapport JSON et comparer les deux ratios séparément — ce que fait ce script.

Contexte : jusqu'au 2026-07-29, la CI lançait `pytest -q` **sans** `--cov`.
Le `fail_under = 95` du projet n'avait donc jamais été évalué une seule fois,
et les branches n'étaient pas mesurées du tout (elles étaient à 94,8 %, sous
la barre, sans que rien ne le signale). Ce script est la moitié « mesure » du
garde-fou ; l'autre moitié est l'étape `--cov` dans `.github/workflows/ci.yml`.

Usage :
    pytest tests/ --cov=tools --cov-branch --cov-report=json
    python scripts/check_coverage.py --min 95
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

#: Métriques vérifiées : clé dans `totals`, libellé, et de quoi chiffrer le
#: manque (total, couvert) pour que le message d'échec soit actionnable.
METRIQUES = (
    ("percent_statements_covered", "statements", "num_statements", "covered_lines"),
    ("percent_branches_covered", "branches", "num_branches", "covered_branches"),
)


def _forcer_sortie_utf8() -> None:
    """Évite un `UnicodeEncodeError` sur console Windows (cp1252).

    Les messages sont en français et le rapport affiche des symboles hors
    Latin-1. Sans ça, le script PLANTE au moment d'annoncer un succès — ce qui
    ferait échouer une CI dont la couverture est pourtant bonne, et donnerait
    une erreur incompréhensible à qui le lance à la main sous Windows.
    """
    for flux in (sys.stdout, sys.stderr):
        reconfigure = getattr(flux, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Échoue si une métrique de couverture passe sous le seuil.",
    )
    p.add_argument(
        "--input",
        default="coverage.json",
        help="Rapport JSON produit par `--cov-report=json` (défaut : coverage.json).",
    )
    p.add_argument(
        "--min",
        type=float,
        default=95.0,
        help="Seuil appliqué à CHAQUE métrique (défaut : 95).",
    )
    return p


def _echec(message: str) -> int:
    """Échec bruyant. Un garde-fou qui se tait quand il ne peut pas mesurer
    est pire que pas de garde-fou : il rend la CI verte par accident."""
    print(f"[couverture] ECHEC — {message}")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    _forcer_sortie_utf8()
    args = build_parser().parse_args(argv)
    chemin = Path(args.input)

    if not chemin.is_file():
        return _echec(
            f"rapport introuvable : {chemin}. La couverture n'a pas été mesurée "
            "(l'étape pytest a-t-elle bien `--cov-report=json` ?)."
        )
    try:
        rapport = json.loads(chemin.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return _echec(f"rapport illisible ({chemin}) : {exc}")

    totals = rapport.get("totals")
    if not isinstance(totals, dict):
        return _echec(f"rapport sans section `totals` : {chemin}")

    manquantes: list[str] = []
    lignes: list[str] = []
    for cle, libelle, cle_total, cle_couvert in METRIQUES:
        valeur = totals.get(cle)
        if not isinstance(valeur, (int, float)):
            manquantes.append(libelle)
            continue
        etat = "OK  " if valeur >= args.min else "SOUS"
        detail = ""
        if valeur < args.min:
            total = totals.get(cle_total) or 0
            couvert = totals.get(cle_couvert) or 0
            besoin = max(0, int(args.min / 100 * total + 0.999) - couvert)
            detail = f" — il en manque {besoin} sur {total} pour atteindre {args.min:g} %"
        lignes.append(f"  {etat} {libelle:11} {valeur:6.2f} % (seuil {args.min:g} %){detail}")

    # On affiche TOUJOURS les deux chiffres : une CI verte muette laisse la
    # dérive s'installer entre deux mesures.
    print("[couverture] Python, métrique par métrique :")
    for ligne in lignes:
        print(ligne)

    if manquantes:
        return _echec(
            "métrique(s) absente(s) du rapport : " + ", ".join(manquantes)
            + ". `--cov-branch` est-il bien passé à pytest ?"
        )
    if any(ligne.lstrip().startswith("SOUS") for ligne in lignes):
        return _echec(f"au moins une métrique est sous le seuil de {args.min:g} %.")

    print(f"[couverture] OK — les {len(METRIQUES)} métriques sont ≥ {args.min:g} %.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
