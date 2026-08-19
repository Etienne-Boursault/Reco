"""
aligner_types_item_reco.py — faire dire la meme chose aux deux collections.

LE DEFAUT
---------
Une oeuvre porte ses types a deux endroits : sur l'ITEM (`src/content/items/`)
et sur chacune de ses RECOS (`src/content/recos/`). Les galeries lisent
l'item, les cartes de `/recos` lisent la reco. Les deux ont diverge : 120
oeuvres visibles disaient une chose d'un cote et une autre de l'autre —
« Takeshi Castle » etait une video pour la galerie et une serie pour la carte.

Releve a la relecture du 2026-08-19, apres la passe sur le fourre-tout
« autre » qui avait mis le probleme au jour.

CE QUI N'EST PAS UN DEFAUT
--------------------------
71 de ces divergences sont benignes : l'item porte PLUS de types que chaque
reco prise isolement, parce qu'il les agrege. 51 viennent d'ailleurs de
`marquer_artistes_musicaux.py`, qui ajoute `musique` aux artistes dont une
reco porte un lien d'ecoute — et n'ecrit que sur les items. Ces cas ne sont
pas dans la table.

LES QUATRE FAMILLES TRAITEES
----------------------------
1. CREATEURS YOUTUBE — l'item disait `video`, la reco `chaine` ou `artiste`.
   Ce sont des chaines ou des personnes, pas des videos isolees. L'editeur :
   « ce sont bien des artistes/chaines qui ont souvent une chaine YT ou voir
   leur media, donc corriger le type mais bien conserver les liens des videos
   associees ». Seul le champ `types` est touche ici — jamais `links`.

2. EMISSIONS DE TELEVISION — le corpus n'avait pas de regle : The Voice etait
   une serie, Takeshi Castle une video, LOL un jeu, True Story un podcast.
   Regle posee et validee : un programme de television non scenarise — jeu,
   telecrochet, telerealite, magazine — est une `video`. `serie` reste aux
   fictions.

3. FILMS TYPES « VIDEO » — quatre documentaires et courts metrages.

4. UNIONS — quand les deux lectures sont vraies a la fois. « pour les cas
   artistes + {autre_type}, ca ne me gene pas de garder les deux » : Verino
   est un artiste ET une chaine, Guillermo Guiz un artiste ET un spectacle.

5. ARBITRAGES — « Fouloscopie » portait deux fiches et trois types plausibles.
   Arbitre : une seule fiche, `chaine` + `livre` + `video`. Mehdi Moussaid
   tient une chaine de vulgarisation, a publie un livre du meme nom, et les
   recos pointent aussi des videos precises.

CE QUI N'EST PAS ICI
--------------------
Les doublons d'items : ils relevent de `fusionner_doublons_cures.py`, qui
doit passer AVANT — fusionner deux fiches reporte les mentions de l'une sur
l'autre, et change donc les recos qu'une decision ici doit aligner.
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

log = logging.getLogger("aligner_types")

#: L'enum `itemType` de `src/content.config.ts`.
TYPES_ADMIS = frozenset({
    "film", "serie", "livre", "bd", "musique", "album", "artiste", "podcast",
    "video", "chaine", "jeu", "spectacle", "lieu", "application", "autre",
})

CHEMIN_TABLE = Path(__file__).resolve().parent / "data" / "types_alignes.json"


def charger_table(chemin: Path = CHEMIN_TABLE) -> list[dict[str, Any]]:
    """Lit la table de decisions. Refuse tout ce qui n'est pas exploitable."""
    table = json.loads(chemin.read_text(encoding="utf-8"))
    vus: set[str] = set()
    for ligne in table:
        item_id = ligne.get("id")
        if not item_id:
            raise ValueError("decision sans id")
        if item_id in vus:
            raise ValueError(f"{item_id} : decision en double")
        vus.add(item_id)
        cible = ligne.get("cible")
        if not isinstance(cible, list) or not cible:
            raise ValueError(f"{item_id} : cible vide")
        if len(set(cible)) != len(cible):
            raise ValueError(f"{item_id} : type repete dans {cible}")
        inconnus = [t for t in cible if t not in TYPES_ADMIS]
        if inconnus:
            raise ValueError(f"{item_id} : type(s) hors enum {inconnus}")
    return table


def _ecrire(chemin: Path, doc: dict[str, Any]) -> None:
    chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def _index_mentions() -> dict[str, list[str]]:
    """itemId -> ids de ses mentions publiques.

    Mention et reco partagent leur identifiant : les mentions ne portent pas
    de `recoId`, c'est la seule jointure entre les deux collections.
    """
    index: dict[str, list[str]] = collections.defaultdict(list)
    for chemin in common.MENTIONS_DIR.rglob("*.json"):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if doc.get("status") == "discarded":
            continue
        index[doc.get("itemId", "")].append(doc.get("id", ""))
    return dict(index)


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


def executer(table: Sequence[dict[str, Any]], *, apply: bool) -> dict[str, Any]:
    """Aligne items et recos sur la table. Renvoie un rapport."""
    items = _fichiers_par_id(common.ITEMS_DIR)
    recos = _fichiers_par_id(common.RECOS_DIR)
    mentions = _index_mentions()

    rapport: dict[str, Any] = {"items": 0, "recos": 0, "refus": [],
                               "par_motif": collections.Counter()}
    for ligne in table:
        item_id, cible = ligne["id"], list(ligne["cible"])
        chemin = items.get(item_id)
        if chemin is None:
            rapport["refus"].append(f"{item_id} : item introuvable")
            continue
        doc = json.loads(chemin.read_text(encoding="utf-8"))
        attendu = ligne.get("avant_item")
        actuels = sorted(doc.get("types") or [])
        # Le controle de peremption ne se declenche que si les types actuels
        # ne sont NI l'etat de depart, NI la cible. Sans cette seconde
        # tolerance, une passe rejouee refuserait tout ce qu'elle vient
        # d'appliquer, et le journal noierait les vrais conflits.
        if (attendu is not None and actuels != sorted(attendu)
                and actuels != sorted(cible)):
            rapport["refus"].append(
                f"{item_id} « {doc.get('title')} » : types inattendus "
                f"{doc.get('types')}, la table attendait {attendu}")
            continue

        if sorted(doc.get("types") or []) != sorted(cible):
            log.info("item %s « %s » : %s -> %s", item_id, doc.get("title"),
                     doc.get("types"), cible)
            rapport["items"] += 1
            rapport["par_motif"][ligne.get("motif", "?")] += 1
            if apply:
                doc["types"] = cible
                _ecrire(chemin, doc)

        # Les recos de cette oeuvre suivent. Seul `types` bouge : les liens,
        # y compris ceux des videos, restent tels quels.
        for mention_id in mentions.get(item_id, []):
            chemin_reco = recos.get(mention_id)
            if chemin_reco is None:
                continue
            reco = json.loads(chemin_reco.read_text(encoding="utf-8"))
            if sorted(reco.get("types") or []) == sorted(cible):
                continue
            log.info("  reco %s : %s -> %s", mention_id, reco.get("types"), cible)
            rapport["recos"] += 1
            if apply:
                reco["types"] = cible
                _ecrire(chemin_reco, reco)
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aligne les types d'une oeuvre et de ses recommandations "
                    "sur une table de decisions curee.")
    parser.add_argument("--table", type=Path, default=CHEMIN_TABLE,
                        help="fichier JSON de decisions")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        table = charger_table(args.table)
    except (OSError, ValueError, json.JSONDecodeError) as erreur:
        log.error("table refusee : %s", erreur)
        return 1
    rapport = executer(table, apply=args.apply)
    log.info("%d item(s) et %d reco(s) alignee(s)", rapport["items"], rapport["recos"])
    for motif, n in sorted(rapport["par_motif"].items()):
        log.info("   %-20s %d", motif, n)
    for refus in rapport["refus"]:
        log.warning("REFUS %s", refus)
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
