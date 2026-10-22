"""
pricing.py — coût d'un appel à partir de jetons OBSERVÉS et d'un tarif DATÉ.

Aucun tarif n'est écrit dans le code : ils vivent dans `tarifs.json`, versionné
(`pricing_version`, `valid_from`, source, date de relevé). Un appel est valorisé
par le tarif en vigueur à sa date, jamais par celui du jour : un rapport
recalculé le mois suivant donne le même montant.

Calcul en `Decimal`, sans arrondi par appel (des micro-coûts arrondis à zéro
puis sommés feraient un total faux). L'arrondi se fait une fois, au rapport.

Pas de coût sans fondement :
  - jetons non rendus par le fournisseur -> coût inconnu (`None`) ;
  - modèle ou transport sans tarif -> coût inconnu ;
  - jetons de cache sans prix de cache relevé -> coût inconnu.
Jamais `0` par défaut.
"""
from __future__ import annotations

import functools
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

TARIFS = Path(__file__).with_name("tarifs.json")
_DATEE = re.compile(r"-\d{8}$")
MILLION = Decimal(1_000_000)


@functools.cache
def _charger(chemin: str) -> dict[str, Any]:
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def tarifs(chemin: Path = TARIFS) -> dict[str, Any]:
    return _charger(str(chemin))


def tarif(provider: str, model: str, transport: str, at: str,
          chemin: Path = TARIFS) -> dict[str, Any] | None:
    """Le tarif en vigueur à la date `at` (ISO), ou None.

    Une version datée (`claude-x-20251001`) prend le tarif de son alias.
    """
    table = tarifs(chemin)
    jour = at[:10]
    candidats = [e for e in table["entries"]
                 if e["provider"] == provider and e["transport"] == transport
                 and e["model"] in {model, _DATEE.sub("", model)} and e["valid_from"] <= jour]
    if not candidats:
        return None
    entree = max(candidats, key=lambda e: e["valid_from"])
    return {**entree, "currency": table["currency"], "pricing_version": table["pricing_version"]}


def snapshot_id(entree: dict[str, Any]) -> str:
    return (f"{entree['pricing_version']}:{entree['provider']}:{entree['model']}:"
            f"{entree['transport']}:{entree['valid_from']}")


def cout(entree: dict[str, Any] | None, usage: dict[str, Any]) -> Decimal | None:
    """Coût exact d'un usage observé, ou None s'il n'est pas fondé."""
    if entree is None:
        return None
    entree_tok, sortie_tok = usage.get("input_tokens"), usage.get("output_tokens")
    if entree_tok is None or sortie_tok is None:
        return None
    total = (Decimal(entree_tok) * Decimal(entree["input"])
             + Decimal(sortie_tok) * Decimal(entree["output"]))
    for jetons, prix in (("cache_read_input_tokens", "cache_read"),
                         ("cache_write_input_tokens", "cache_write")):
        n = usage.get(jetons) or 0
        if n:
            if entree.get(prix) is None:
                return None
            total += Decimal(n) * Decimal(entree[prix])
    return total / MILLION
