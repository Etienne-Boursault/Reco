"""
attribuer_mentions_sans_reco.py — rendre huit mentions a leur auteur.

D'OU VIENNENT CES HUIT CAS
--------------------------
Une mention dit « telle personne a parle de telle oeuvre dans tel episode ».
La recommandation, elle, porte le titre, le createur, les liens. Huit mentions
publiees n'ont pas de recommandation : leur fichier est absent, pas vide.

Elles s'affichent donc dans la chronologie d'une fiche d'oeuvre avec un nom
approximatif — « Nassim », « Kyan », « N/A » — et rien d'autre. Repere le
2026-08-19 en corrigeant « Balade Mentale ».

CE QUE LES TRANSCRIPTS NE POUVAIENT PAS DIRE
--------------------------------------------
Le corpus n'est pas diarize : rien, dans le texte, ne dit qui parle. C'est
pour cela que `recommendedBy` etait tantot vide, tantot approximatif. Chaque
ligne ci-dessous a ete tranchee A L'OREILLE par l'editeur, en ecoutant
l'episode au timecode de la mention.

DEUX D'ENTRE ELLES DISAIENT LA MEME CHOSE
-----------------------------------------
`ubm-0525` et `ubm-1559` pointent le meme instant (00:31:44), la meme phrase
— « dernier coup de coeur, la zone d'interet » — mais etaient rattachees a
deux fiches differentes, l'une sous son titre francais, l'autre sous
l'anglais. La seconde est ecartee ; les fiches fusionnent par ailleurs.

DEUX N'ETAIENT PAS DES RECOMMANDATIONS
--------------------------------------
« Marvel » et « Visionnaire » sont des mentions de passage, pas des conseils.
Elles passent en `citation` : le site les affiche alors comme « mentionne »
et non « recommande ».
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

log = logging.getLogger("attributions_mentions")


@dataclass(frozen=True)
class Attribution:
    """Ce qu'il faut poser sur une mention, et pourquoi."""
    mention_id: str
    oeuvre: str
    #: Qui parle, entendu par l'editeur au timecode de la mention.
    par: str | None = None
    #: `citation` quand l'oeuvre est mentionnee sans etre conseillee.
    kind: str | None = None
    #: L'oeuvre est celle d'un·e invite·e de l'episode.
    guest_work: bool = False
    #: Ecarte la mention : elle fait doublon avec une autre.
    ecarter: bool = False
    pourquoi: str = ""


#: Table arbitree a l'oreille par l'editeur le 2026-08-19.
ATTRIBUTIONS: tuple[Attribution, ...] = (
    Attribution("ubm-0518", "Bagarre", par="Nassim Lyes",
                pourquoi="etait attribuee a Navo"),
    Attribution("ubm-0525", "La Zone d'intérêt", par="Kyan Khojandi",
                pourquoi="le champ valait « N/A »"),
    Attribution("ubm-0540", "Marvel", par="Kyan Khojandi", kind="citation",
                pourquoi="mention de passage, pas un conseil"),
    Attribution("ubm-1357", "Visionnaire", par="Navo", kind="citation",
                pourquoi="mention de passage ; etait attribuee a Kyan"),
    Attribution("ubm-1362", "Balade Mentale", par="Kyan Khojandi",
                pourquoi="etait attribuee a « Nassim »"),
    Attribution("ubm-1559", "The Zone of Interest", ecarter=True,
                pourquoi="meme instant et meme phrase que ubm-0525"),
    Attribution("ubm-1560", "Chaîne Christophe Pauly", par="Kyan Khojandi",
                pourquoi="etait attribuee a « Kyan », nom tronque ; les deux "
                         "chaines sont citees dans la meme phrase"),
    Attribution("ubm-2091", "Message Personnel", par="Kyan Khojandi",
                guest_work=True,
                pourquoi="etait attribuee a « Jessé » ; l'oeuvre est celle "
                         "d'un·e invite·e de l'episode"),
)


def _ecrire(chemin: Path, doc: dict[str, Any]) -> None:
    chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def appliquer(doc: dict[str, Any], a: Attribution) -> list[str]:
    """Pose l'attribution sur une mention. Renvoie les champs touches."""
    touches: list[str] = []
    if a.ecarter:
        if doc.get("status") != "discarded":
            doc["status"] = "discarded"
            touches.append("status")
        return touches
    if a.par is not None and doc.get("recommendedBy") != a.par:
        doc["recommendedBy"] = a.par
        touches.append("recommendedBy")
    if a.kind is not None and doc.get("kind") != a.kind:
        doc["kind"] = a.kind
        touches.append("kind")
    # `guestWork` n'est jamais pose a False : le schema l'admet nullable, mais
    # une valeur explicite dirait « verifie et non », ce qui n'est pas le cas.
    if a.guest_work and doc.get("guestWork") is not True:
        doc["guestWork"] = True
        touches.append("guestWork")
    return touches


def executer(attributions: Sequence[Attribution], *, apply: bool) -> dict[str, Any]:
    """Applique la table aux mentions. Renvoie un rapport."""
    par_id = {a.mention_id: a for a in attributions}
    rapport: dict[str, Any] = {"mentions": 0, "ecartees": 0, "refus": []}
    vues: set[str] = set()
    for chemin in sorted(common.MENTIONS_DIR.rglob("*.json")):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        a = par_id.get(doc.get("id", ""))
        if a is None:
            continue
        vues.add(a.mention_id)
        touches = appliquer(doc, a)
        if not touches:
            continue
        log.info("%s « %s » : %s", a.mention_id, a.oeuvre, ", ".join(touches))
        if a.ecarter:
            rapport["ecartees"] += 1
        else:
            rapport["mentions"] += 1
        if apply:
            _ecrire(chemin, doc)
    for manquante in sorted(set(par_id) - vues):
        rapport["refus"].append(f"{manquante} : mention introuvable")
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pose sur huit mentions l'auteur entendu par l'editeur, "
                    "et ecarte celle qui faisait doublon.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(ATTRIBUTIONS, apply=args.apply)
    log.info("%d mention(s) attribuee(s), %d ecartee(s)",
             rapport["mentions"], rapport["ecartees"])
    for refus in rapport["refus"]:
        log.warning("REFUS %s", refus)
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
