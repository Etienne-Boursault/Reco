"""
aligner_titres_item_reco.py — l'oeuvre reprend le titre que sa reco a corrige.

CE QUE LA RELECTURE A VU
------------------------
Sur la fiche d'une oeuvre de Kyan Khojandi, la section « du meme createur »
proposait « Agendas ». Or ce titre n'existe nulle part ailleurs : « quand je
filtre dans les recos, je ne la trouve pas et je trouve bien Haagen-Dazs »
(2026-08-19). C'est le nom d'un morceau, mal entendu par la transcription puis
corrige — sur la RECO seulement.

Quinze oeuvres sont dans ce cas. Le titre corrige vit sur la recommandation ;
la fiche d'oeuvre, elle, porte encore la graphie du transcript : « Diams »
pour « Diam's », « Mister Nobody » pour « Mr. Nobody », « Aliosha Schneider »
pour « Aliocha Schneider », « Vincent Delerme » pour « Vincent Delerm ».

POURQUOI LA RECO A RAISON — SAUF QUAND ELLE A TORT
--------------------------------------------------
Les recommandations ont ete relues et corrigees une par une lors des vagues de
juillet et d'aout ; les fiches d'oeuvre, non. Le sens de propagation par
defaut va donc de la reco vers l'oeuvre.

Une exception verifiee : « La Zone d'interet ». La reco porte le titre anglais
« Zone of Interest » alors que la fiche porte le titre francais, celui
qu'emploient AlloCine et SOONER — les deux liens de la reco elle-meme. Ici
c'est l'OEUVRE qui a raison, et la reco qui la suit.

CE QUI NE PASSE PAS PAR ICI
---------------------------
Une oeuvre dont les recos ne s'accordent pas entre elles sur le titre : ce
serait un desaccord, pas une correction, et le script le signale sans agir.
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

log = logging.getLogger("aligner_titres")

#: Les oeuvres ou c'est la FICHE qui a raison : la reco reprendra son titre.
#: Chaque entree porte la source qui tranche.
L_OEUVRE_A_RAISON: dict[str, str] = {
    # « La Zone d'interet » est le titre francais, celui d'AlloCine (fiche
    # 266159) et de SOONER — les deux liens que la reco porte elle-meme.
    "815746f1": "https://www.allocine.fr/film/fichefilm_gen_cfilm=266159.html",
}


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


def _norm(titre: str | None) -> str:
    return (titre or "").strip().casefold()


def executer(*, apply: bool) -> dict[str, Any]:
    """Aligne le titre d'une oeuvre et celui de ses recos."""
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

    rapport: dict[str, Any] = {"items": 0, "recos": 0, "desaccords": []}
    for item_id, mention_ids in sorted(par_item.items()):
        if item_id not in items:
            continue
        chemin_item, item = items[item_id]
        presentes = [(m, recos[m][1]) for m in sorted(mention_ids) if m in recos]
        if item_id in L_OEUVRE_A_RAISON:
            # Sens inverse : la fiche porte le bon titre, les recos suivent.
            # Ce cas passe AVANT tous les autres controles : quand la fiche
            # fait autorite, peu importe que ses recos s'accordent entre
            # elles, ni que l'une porte deja le bon titre.
            cible = item.get("title")
            for reco_id, doc in presentes:
                if doc.get("title") == cible:
                    continue
                log.info("reco %s : %r -> %r (l'oeuvre avait raison)",
                         reco_id, doc.get("title"), cible)
                doc["title"] = cible
                rapport["recos"] += 1
                if apply:
                    _ecrire(recos[reco_id][0], doc)
            continue

        titres = {_norm(doc.get("title")) for _, doc in presentes if doc.get("title")}
        titres.discard("")
        if not titres or _norm(item.get("title")) in titres:
            continue
        if len(titres) > 1:
            # Les recos ne s'accordent pas : ce n'est pas une correction,
            # et rien ici ne permet de trancher entre elles.
            rapport["desaccords"].append(
                f"{item_id} « {item.get('title')} » : recos {sorted(titres)}")
            continue

        cible = next(doc["title"] for _, doc in presentes if doc.get("title"))
        log.info("item %s : %r -> %r", item_id, item.get("title"), cible)
        item["title"] = cible
        rapport["items"] += 1
        if apply:
            _ecrire(chemin_item, item)
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Donne a chaque oeuvre le titre que ses recommandations "
                    "portent, celles-ci ayant ete relues une par une.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(apply=args.apply)
    log.info("%d titre(s) d'oeuvre et %d titre(s) de reco alignes",
             rapport["items"], rapport["recos"])
    for d in rapport["desaccords"]:
        log.warning("DESACCORD %s", d)
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
