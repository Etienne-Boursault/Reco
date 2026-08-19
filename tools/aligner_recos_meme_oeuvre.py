"""
aligner_recos_meme_oeuvre.py — une oeuvre, un createur, un jeu de liens.

CE QUE LA RELECTURE A VU
------------------------
Sur la fiche d'une oeuvre, ses recommandations s'affichent cote a cote. Elles
devraient se ressembler : c'est la meme oeuvre. Elles ne se ressemblaient pas.

« Balade Mentale » : trois cartes, l'une avec un createur, deux sans, et des
jeux de liens de un a trois. « LOL » : deux cartes, l'une creditee a celui qui
la recommande. « Fouloscopie » : trois cartes portant un, trois et trois liens.
Releve le 2026-08-19 — « certaines avec des liens incomplets ».

Chaque recommandation est bien une MENTION distincte, et c'est normal. Mais
l'oeuvre, elle, est la meme : rien ne justifie qu'elle change de createur ou
de liens d'une carte a l'autre.

CE QUE FAIT CETTE PASSE
-----------------------
LES LIENS : l'UNION de ce que portent les recommandations, dans l'ordre de
leur premiere apparition. Cet ordre a ete pose a la main lors des vagues de
verification ; le remplacer par un tri alphabetique perdrait cette
information. Aucun lien n'est retire — seulement ajoute a celles qui en
manquaient.

LE CREATEUR : le plus COMPLET, a condition qu'il CONTIENNE les autres.
« Vince Gilligan » face a « Vince Gilligan, Peter Gould » n'est pas un
desaccord, c'est une liste tronquee, et la page doit crediter toute l'equipe.
Deux noms qui ne s'emboitent pas restent un desaccord : la passe les SIGNALE
et n'y touche pas. C'est la meme regle que `fusion_items_doublons.fusionner`.

CE QU'ELLE NE FAIT PAS
----------------------
Elle ne corrige pas un createur FAUX — « Christophe Pauly » pour Balade
Mentale, « Paul de Saint Sernin » pour LOL. Propager une erreur a toutes les
cartes d'une oeuvre est pire que de la laisser sur une seule.
`corriger_attributions_erronees.py` s'en charge, et doit passer AVANT.
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

log = logging.getLogger("aligner_recos")


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


def noms(createur: str | None) -> set[str]:
    """Les noms d'une liste de createurs, normalises pour la comparaison."""
    if not createur:
        return set()
    return {n.strip().casefold() for n in createur.split(",") if n.strip()}


def createur_le_plus_complet(valeurs: Sequence[str | None]) -> str | None:
    """La graphie qui CONTIENT toutes les autres, ou `None` si desaccord.

    Renvoie `None` aussi quand aucune valeur n'est renseignee : il n'y a alors
    rien a propager.
    """
    renseignes = [v for v in valeurs if v and v.strip()]
    if not renseignes:
        return None
    candidat = max(renseignes, key=lambda v: len(noms(v)))
    reference = noms(candidat)
    for autre in renseignes:
        if not noms(autre) <= reference:
            return None  # deux listes qui ne s'emboitent pas : desaccord
    return candidat


def union_des_liens(par_reco: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Tous les liens, sans doublon d'URL, dans l'ordre de premiere apparition."""
    vus: dict[str, dict[str, Any]] = {}
    for liens in par_reco:
        for lien in liens or []:
            url = lien.get("url") if isinstance(lien, dict) else None
            if not url or url in vus:
                continue
            vus[url] = dict(lien)
    return list(vus.values())


def executer(*, apply: bool) -> dict[str, Any]:
    """Aligne createur et liens entre les recos d'une meme oeuvre."""
    recos = _charger(common.RECOS_DIR)
    par_item: dict[str, list[str]] = collections.defaultdict(list)
    for chemin in common.MENTIONS_DIR.rglob("*.json"):
        try:
            mention = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # Une reco ecartee ne s'affiche nulle part : ni source, ni cible.
        if mention.get("status") == "discarded":
            continue
        par_item[mention.get("itemId", "")].append(mention.get("id", ""))

    rapport: dict[str, Any] = {"oeuvres": 0, "recos_createur": 0,
                               "recos_liens": 0, "desaccords": []}
    for item_id, ids in sorted(par_item.items()):
        presentes = [(i, recos[i][1]) for i in sorted(ids) if i in recos]
        if len(presentes) < 2:
            continue

        cible_createur = createur_le_plus_complet(
            [doc.get("creator") for _, doc in presentes])
        divergent = len({(doc.get("creator") or "").strip()
                         for _, doc in presentes}) > 1
        if divergent and cible_createur is None:
            rapport["desaccords"].append(
                f"{item_id} « {presentes[0][1].get('title')} » : "
                f"{sorted({(d.get('creator') or '—') for _, d in presentes})}")

        cible_liens = union_des_liens([doc.get("links") or []
                                       for _, doc in presentes])

        touchee = False
        for reco_id, doc in presentes:
            change = []
            if cible_createur and doc.get("creator") != cible_createur:
                doc["creator"] = cible_createur
                rapport["recos_createur"] += 1
                change.append("creator")
            urls = [lien.get("url") for lien in (doc.get("links") or [])
                    if isinstance(lien, dict)]
            if urls != [lien["url"] for lien in cible_liens]:
                doc["links"] = [dict(lien) for lien in cible_liens]
                rapport["recos_liens"] += 1
                change.append(f"links {len(urls)} -> {len(cible_liens)}")
            if not change:
                continue
            touchee = True
            log.info("  %s : %s", reco_id, ", ".join(change))
            if apply:
                _ecrire(recos[reco_id][0], doc)
        if touchee:
            rapport["oeuvres"] += 1
            log.info("%s « %s » alignee", item_id, presentes[0][1].get("title"))
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Donne le meme createur et le meme jeu de liens a toutes "
                    "les recommandations d'une meme oeuvre.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(apply=args.apply)
    log.info("%d oeuvre(s) alignee(s) : %d createur(s), %d jeu(x) de liens",
             rapport["oeuvres"], rapport["recos_createur"],
             rapport["recos_liens"])
    for d in rapport["desaccords"]:
        log.warning("DESACCORD %s", d)
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
