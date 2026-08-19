"""
propager_types_vers_recos.py — la carte dit ce que la galerie dit.

LE DEFAUT
---------
Soixante-dix oeuvres portent plus de types sur leur FICHE que sur chacune de
leurs recommandations. Ce n'est pas une contradiction — la fiche agrege ce que
plusieurs recommandations disent separement — mais le visiteur, lui, voit une
incoherence : Yseult figure dans `/musique` et dans `/artistes`, alors que sa
carte sur `/recos` ne porte que la puce « artiste ». Qui filtre `/recos` sur
« musique » ne la trouve donc pas.

Cinquante et une de ces divergences viennent de `marquer_artistes_musicaux`,
qui ajoute `musique` aux artistes dont une reco porte un lien d'ecoute — et
n'ecrit que sur les fiches.

Arbitre le 2026-08-19 : « j'ai une preference pour la propagation ».

CE QUE FAIT LA PASSE
--------------------
Elle ne propage QUE dans ce sens-la : une reco recoit les types que la fiche
porte en plus. Elle n'en retire jamais, et ne touche pas une oeuvre dont la
fiche en porte MOINS que ses recos — ce cas releve d'un autre arbitrage
(`aligner_types_item_reco.py`).

ET LES LIENS AVEC
-----------------
« N'oublie pas d'aligner les liens » : une reco qui gagne le type `musique`
sans gagner le lien d'ecoute qui l'a justifie serait un progres a moitie. La
passe reprend donc l'union des liens de l'oeuvre, comme
`aligner_recos_meme_oeuvre`, pour les seules oeuvres qu'elle touche.
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common
from aligner_recos_meme_oeuvre import union_des_liens

log = logging.getLogger("propager_types")


def _charger(racine: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    trouves: dict[str, tuple[Path, dict[str, Any]]] = {}
    for chemin in racine.rglob("*.json"):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if doc.get("id"):
            trouves[doc["id"]] = (chemin, doc)
    return trouves


def _ecrire(chemin: Path, doc: dict[str, Any]) -> None:
    chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def executer(*, apply: bool) -> dict[str, Any]:
    """Propage les types de la fiche vers ses recos. Renvoie un rapport."""
    items = _charger(common.ITEMS_DIR)
    recos = _charger(common.RECOS_DIR)
    par_item: dict[str, list[str]] = collections.defaultdict(list)
    for chemin in common.MENTIONS_DIR.rglob("*.json"):
        try:
            mention = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if mention.get("status") == "discarded":
            continue
        par_item[mention.get("itemId", "")].append(mention.get("id", ""))

    rapport: dict[str, Any] = {"oeuvres": 0, "recos_types": 0, "recos_liens": 0}
    for item_id, mention_ids in sorted(par_item.items()):
        if item_id not in items:
            continue
        item = items[item_id][1]
        presentes = [(m, recos[m][1]) for m in sorted(mention_ids) if m in recos]
        avec_types = [doc for _, doc in presentes if doc.get("types")]
        if not avec_types:
            continue

        cible = list(item.get("types") or [])
        if not cible:
            continue
        # Deux conditions, et la seconde compte autant que la premiere :
        #
        #  1. AUCUNE reco ne porte un type absent de la fiche. Le cas inverse
        #     — une reco plus riche — releve d'un arbitrage, pas d'une
        #     propagation : on ne retire jamais.
        #  2. au moins une reco a quelque chose a gagner.
        #
        # Comparer a l'UNION des recos ne suffit pas : si l'une d'elles est
        # deja alignee, l'union egale la cible et les autres restent en
        # arriere. C'est un test qui l'a montre.
        if any(not set(doc["types"]) <= set(cible) for doc in avec_types):
            continue
        if all(set(doc["types"]) == set(cible) for doc in avec_types):
            continue

        cible_liens = union_des_liens([doc.get("links") or []
                                       for _, doc in presentes])
        # Les deux gardes ci-dessus l'assurent : au moins une reco va bouger.
        # Un drapeau « touchee » n'avait donc qu'une valeur possible, et la
        # branche negative etait injoignable — retire plutot que laisse.
        rapport["oeuvres"] += 1
        log.info("%s « %s » -> %s", item_id, item.get("title"), cible)
        for reco_id, doc in presentes:
            change = []
            if sorted(doc.get("types") or []) != sorted(cible):
                doc["types"] = list(cible)
                rapport["recos_types"] += 1
                change.append("types")
            urls = [lien.get("url") for lien in (doc.get("links") or [])
                    if isinstance(lien, dict)]
            if urls != [lien["url"] for lien in cible_liens]:
                doc["links"] = [dict(lien) for lien in cible_liens]
                rapport["recos_liens"] += 1
                change.append(f"links {len(urls)} -> {len(cible_liens)}")
            if not change:
                continue
            log.info("  %s : %s", reco_id, ", ".join(change))
            if apply:
                _ecrire(recos[reco_id][0], doc)
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Donne aux recommandations les types que porte leur "
                    "fiche d'oeuvre, et aligne leurs liens au passage.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(apply=args.apply)
    log.info("%d oeuvre(s) : %d jeu(x) de types, %d jeu(x) de liens",
             rapport["oeuvres"], rapport["recos_types"], rapport["recos_liens"])
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
