"""
appliquer_types_items.py — sortir les oeuvres du fourre-tout « autre ».

CE QUE LA RELECTURE A VU
------------------------
La galerie `/un-bon-moment/autres` affichait 67 oeuvres, dont beaucoup
n'avaient rien de mysterieux : « Pluribus » est une serie, « Hugo Lisoir » une
chaine YouTube, « Procreate » une application. Demande du 2026-08-19 : « il y
en a beaucoup qui ont l'air d'etre un autre type, je te laisse corriger et
remettre les categories dans leurs bonnes categories (certaines de ces recos
doivent rester "Autres") ».

L'ANALYSE EST AILLEURS, L'ECRITURE EST ICI
------------------------------------------
Trois agents ont examine les 67 oeuvres et rendu un verdict par oeuvre :
types proposes, justification, et une URL de preuve reellement ouverte. Ce
script ne fait qu'appliquer ces verdicts, comme `apply_links.py` et
`apply_verdicts.py` avant lui. Aucun agent n'ecrit dans `src/content/`.

POURQUOI L'ITEM *ET* LA RECO
----------------------------
Les deux collections portent un champ `types`, et elles ont divergé : 43 des
67 items « autre » avaient deja une reco correctement typee. La galerie lit
l'item, la carte de `/recos` lit la reco — d'ou une oeuvre affichee « serie »
sur une page et rangee dans « autres » sur l'autre.

Ce script aligne les deux, mais dans un seul sens : il ne touche une reco que
si elle est elle-meme en `["autre"]`. Une reco deja typee a ete curee, et rien
ici ne justifie de la reecrire.

GARDES-FOUS
-----------
- Refus si l'item n'est plus en `["autre"]` : le corpus a bougé depuis
  l'analyse, et appliquer un verdict perime ecraserait un travail plus recent.
- Refus de tout type hors de l'enum `itemType` de `src/content.config.ts`.
- Refus d'une liste de types vide.
- Simulation par defaut ; `--apply` pour ecrire.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

log = logging.getLogger("types_items")

#: L'enum `itemType` de `src/content.config.ts`. Y ajouter un type coute six
#: endroits dans le projet : on ne l'elargit pas depuis ici.
TYPES_ADMIS = frozenset({
    "film", "serie", "livre", "bd", "musique", "album", "artiste", "podcast",
    "video", "chaine", "jeu", "spectacle", "lieu", "application", "autre",
})

#: Le type de depart. Un verdict ne s'applique qu'a une oeuvre encore ici.
TYPE_FOURRE_TOUT = ["autre"]


class VerdictInvalide(ValueError):
    """Un verdict que l'on refuse d'appliquer, avec sa raison."""


def valider(verdict: dict[str, Any]) -> list[str]:
    """Renvoie les types a poser. Leve `VerdictInvalide` si le verdict cloche."""
    item_id = verdict.get("itemId")
    if not item_id:
        raise VerdictInvalide("verdict sans itemId")
    types = verdict.get("typesProposes")
    if not isinstance(types, list) or not types:
        raise VerdictInvalide(f"{item_id} : typesProposes vide ou absent")
    inconnus = [t for t in types if t not in TYPES_ADMIS]
    if inconnus:
        raise VerdictInvalide(f"{item_id} : type(s) hors enum {inconnus}")
    if len(set(types)) != len(types):
        raise VerdictInvalide(f"{item_id} : type repete {types}")
    return types


def charger(chemins: Sequence[Path]) -> list[dict[str, Any]]:
    """Concatene les fichiers de verdicts. Refuse un item vu deux fois."""
    tous: list[dict[str, Any]] = []
    vus: set[str] = set()
    for chemin in chemins:
        for verdict in json.loads(chemin.read_text(encoding="utf-8")):
            item_id = verdict.get("itemId")
            if item_id in vus:
                raise VerdictInvalide(f"{item_id} : verdict en double")
            vus.add(item_id)
            tous.append(verdict)
    return tous


def _index_mentions() -> dict[str, list[str]]:
    """itemId -> ids de ses mentions publiques.

    La mention et la reco partagent leur identifiant (`ubm-XXXX`) : c'est la
    seule jointure entre les deux collections, les mentions ne portant pas de
    `recoId`.
    """
    index: dict[str, list[str]] = {}
    for chemin in common.MENTIONS_DIR.rglob("*.json"):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if doc.get("status") == "discarded":
            continue
        index.setdefault(doc.get("itemId", ""), []).append(doc.get("id", ""))
    return index


def _fichiers_par_id(racine: Path) -> dict[str, Path]:
    trouves: dict[str, Path] = {}
    for chemin in racine.rglob("*.json"):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if doc.get("id"):
            trouves[doc["id"]] = chemin
    return trouves


def _ecrire(chemin: Path, doc: dict[str, Any]) -> None:
    chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def executer(verdicts: Sequence[dict[str, Any]], *, apply: bool) -> dict[str, Any]:
    """Applique les verdicts. Renvoie un rapport chiffre."""
    items = _fichiers_par_id(common.ITEMS_DIR)
    recos = _fichiers_par_id(common.RECOS_DIR)
    mentions = _index_mentions()

    rapport: dict[str, Any] = {
        "items_modifies": 0, "recos_modifiees": 0,
        "maintenus_autre": 0, "refus": [],
    }
    for verdict in verdicts:
        try:
            types = valider(verdict)
        except VerdictInvalide as erreur:
            rapport["refus"].append(str(erreur))
            continue
        item_id = verdict["itemId"]

        chemin = items.get(item_id)
        if chemin is None:
            rapport["refus"].append(f"{item_id} : item introuvable")
            continue
        doc = json.loads(chemin.read_text(encoding="utf-8"))
        if doc.get("types") != TYPE_FOURRE_TOUT:
            # Le corpus a bouge depuis l'analyse : un verdict perime
            # ecraserait un travail plus recent.
            rapport["refus"].append(
                f"{item_id} : n'est plus en « autre » ({doc.get('types')})")
            continue
        if types == TYPE_FOURRE_TOUT:
            rapport["maintenus_autre"] += 1
            continue

        log.info("%s « %s » : autre -> %s", item_id, doc.get("title"), types)
        rapport["items_modifies"] += 1
        if apply:
            doc["types"] = types
            _ecrire(chemin, doc)

        # La reco correspondante, si elle est elle aussi restee au fourre-tout.
        for mention_id in mentions.get(item_id, []):
            chemin_reco = recos.get(mention_id)
            if chemin_reco is None:
                continue
            reco = json.loads(chemin_reco.read_text(encoding="utf-8"))
            if reco.get("types") != TYPE_FOURRE_TOUT:
                continue
            rapport["recos_modifiees"] += 1
            if apply:
                reco["types"] = types
                _ecrire(chemin_reco, reco)
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Applique des verdicts de retypage aux items encore "
                    "ranges dans « autre », et aux recos restees au meme "
                    "fourre-tout.")
    parser.add_argument("verdicts", nargs="+", type=Path,
                        help="fichiers JSON de verdicts")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        verdicts = charger(args.verdicts)
    except VerdictInvalide as erreur:
        log.error("verdicts refuses : %s", erreur)
        return 1
    rapport = executer(verdicts, apply=args.apply)
    log.info("%d item(s) retype(s), %d reco(s) alignee(s), %d maintenu(s) "
             "en « autre »", rapport["items_modifies"],
             rapport["recos_modifiees"], rapport["maintenus_autre"])
    for refus in rapport["refus"]:
        log.warning("REFUS %s", refus)
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
