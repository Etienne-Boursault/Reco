"""
poser_leur_oeuvre.py — l'etoile « Leur oeuvre », des deux cotes a la fois.

LE CHAMP VIT A DEUX ENDROITS
----------------------------
`guestWork` existe sur la MENTION et sur la RECO. La carte de `/recos` lit
celui de la reco, la chronologie d'une fiche d'oeuvre lit celui de la mention.
Une passe qui n'ecrit que d'un cote produit une etoile sur une page et pas sur
l'autre — c'est ce qui s'etait passe.

CE QUE LA RELECTURE A VU (2026-08-19)
-------------------------------------
« Pulsions » : cinq cartes sur neuf portaient l'etoile. Or Kyan Khojandi anime
le podcast — le spectacle est le sien quel que soit l'episode. « Pour Pulsions
il faut mettre "leur oeuvre" sur chacune des cartes, Kyan est toujours present
dans l'emission en tant qu'hote ».

« Invisible » : une carte sur deux. Clement Cotentin est invite dans les deux
episodes, et l'emission est la sienne.

« Valide » : l'inverse. La carte portait l'etoile alors que celui qui
recommande est Hakim Jemili, simple invite — la serie est de Franck
Gastambide. L'etoile ment quand elle designe l'oeuvre de quelqu'un d'autre.

POURQUOI UNE TABLE ET PAS UNE REGLE
-----------------------------------
« L'oeuvre de qui parle dans l'episode » ne se deduit d'aucun champ : il faut
savoir qui est present et a qui appartient l'oeuvre. Les transcripts ne sont
pas diarizes, et la liste des invites ne dit pas qui a cree quoi. Chaque ligne
ci-dessous vient d'un arbitrage de l'editeur.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

log = logging.getLogger("leur_oeuvre")


@dataclass(frozen=True)
class Decision:
    """Une oeuvre, et l'etoile qu'elle doit porter — ou pas."""
    item_id: str
    titre: str
    #: `True` pose l'etoile sur toutes ses mentions publiees, `False` la retire.
    etoile: bool
    pourquoi: str
    #: Ne s'applique qu'a ces recos ; toutes si vide.
    seulement: tuple[str, ...] = ()


DECISIONS: tuple[Decision, ...] = (
    Decision(
        item_id="1c5928e1", titre="Pulsions", etoile=True,
        pourquoi="Kyan Khojandi anime le podcast : le spectacle est le sien "
                 "quel que soit l'episode. Cinq cartes sur neuf le disaient.",
    ),
    Decision(
        item_id="f395a970", titre="Invisible", etoile=True,
        pourquoi="Clement Cotentin est invite dans les deux episodes, et "
                 "l'emission est la sienne. Une carte sur deux le disait.",
    ),
    Decision(
        item_id="af15df89", titre="Validé (Xavier Lacaille)", etoile=True,
        seulement=("ubm-2984",),
        pourquoi="Xavier Lacaille est l'un des quatre co-createurs de la "
                 "serie : quand il la recommande, c'est bien son oeuvre. "
                 "L'etoile etait sur la reco mais pas sur la mention, donc "
                 "visible sur la carte et absente de la chronologie.",
    ),
    Decision(
        item_id="af15df89", titre="Validé", etoile=False,
        seulement=("ubm-2694",),
        pourquoi="Hakim Jemili recommande la serie sans en etre l'auteur — "
                 "elle est de Franck Gastambide. L'etoile ment quand elle "
                 "designe l'oeuvre de quelqu'un d'autre. La carte de Xavier "
                 "Lacaille la garde : il est co-createur.",
    ),
)


def _ecrire(chemin: Path, doc: dict[str, Any]) -> None:
    chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def poser(doc: dict[str, Any], etoile: bool) -> bool:
    """Pose ou retire l'etoile. Renvoie `True` si le document a change.

    Retirer supprime la CLE plutot que d'ecrire `False` : le schema l'admet
    nullable, mais une valeur explicite dirait « verifie et non », alors que
    l'immense majorite des recos n'a jamais ete examinee sous cet angle.
    """
    if etoile:
        if doc.get("guestWork") is True:
            return False
        doc["guestWork"] = True
        return True
    if "guestWork" not in doc:
        return False
    del doc["guestWork"]
    return True


def executer(decisions: Sequence[Decision], *, apply: bool) -> dict[str, Any]:
    """Applique les decisions aux mentions ET a leurs recos."""
    # Deux decisions peuvent viser la MEME oeuvre sur des recos disjointes :
    # « Valide » pose l'etoile sur la carte du co-createur et la retire de
    # celle de l'invite. On indexe donc par (oeuvre, reco) et non par oeuvre.
    ciblees = {(d.item_id, r): d for d in decisions for r in d.seulement}
    toutes = {d.item_id: d for d in decisions if not d.seulement}
    # itemId -> ids de ses mentions publiees. Mention et reco partagent leur
    # identifiant : c'est la seule jointure entre les deux collections.
    concernees: dict[str, Decision] = {}
    rapport: dict[str, Any] = {"mentions": 0, "recos": 0, "refus": []}
    vues: set[str] = set()

    for chemin in sorted(common.MENTIONS_DIR.rglob("*.json")):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if doc.get("status") == "discarded":
            continue
        item_id = doc.get("itemId", "")
        decision = (ciblees.get((item_id, doc.get("id", "")))
                    or toutes.get(item_id))
        if decision is None:
            continue
        vues.add(decision.item_id)
        concernees[doc.get("id", "")] = decision
        if poser(doc, decision.etoile):
            rapport["mentions"] += 1
            log.info("mention %s « %s » : %s", doc.get("id"), decision.titre,
                     "étoile posée" if decision.etoile else "étoile retirée")
            if apply:
                _ecrire(chemin, doc)

    for chemin in sorted(common.RECOS_DIR.rglob("*.json")):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        decision = concernees.get(doc.get("id", ""))
        if decision is None:
            continue
        if poser(doc, decision.etoile):
            rapport["recos"] += 1
            log.info("reco    %s « %s » : %s", doc.get("id"), decision.titre,
                     "étoile posée" if decision.etoile else "étoile retirée")
            if apply:
                _ecrire(chemin, doc)

    for manquante in sorted({d.item_id for d in decisions} - vues):
        rapport["refus"].append(f"{manquante} : aucune mention publiee")
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pose ou retire l'etoile « Leur oeuvre » sur toutes les "
                    "mentions d'une oeuvre, et sur leurs recos.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(DECISIONS, apply=args.apply)
    log.info("%d mention(s) et %d reco(s) modifiee(s)",
             rapport["mentions"], rapport["recos"])
    for refus in rapport["refus"]:
        log.warning("REFUS %s", refus)
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
