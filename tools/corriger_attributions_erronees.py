"""
corriger_attributions_erronees.py — rendre une oeuvre a son auteur.

D'OU VIENNENT CES CAS
---------------------
Trois agents ont relu les 67 oeuvres rangees dans « autre » pour les retyper
(2026-08-19). En cherchant le type, ils ont bute sur des `creator` qui ne
tenaient pas debout — un diffuseur a la place d'un realisateur, un animateur
a la place de l'auteur du film dont il parle.

Ce ne sont PAS des variantes d'orthographe : `fix_creator_aliases.py` fusionne
« Éléonore Costes » et « Eleonore Costes », deux graphies d'une meme personne.
Ici, c'est une personne differente. D'ou une table separee.

CHAQUE LIGNE A ETE VERIFIEE, UNE PAR UNE
----------------------------------------
La verification est reportee dans le champ `preuve`, avec la source ouverte.
Sans elle, cette table ne vaudrait pas mieux que ce qu'elle corrige.

CE QUI N'EST PAS TRAITE ICI
---------------------------
Les graphies fautives de TITRE (« Shage » pour « Shaga », « Dailyo » pour
« Daylio ») et les doublons d'items reperes au passage. Renommer un titre
change l'identite affichee d'une oeuvre et peut casser des rapprochements :
cela demande un arbitrage, pas une passe automatique.
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

log = logging.getLogger("attributions")


@dataclass(frozen=True)
class Correction:
    """Une attribution fautive, sa correction, et la source qui l'atteste."""
    item_id: str
    titre: str
    createur_faux: str
    createur: str
    preuve: str
    annee: int | None = None
    #: Identifiants externes a retirer : ils designent la mauvaise personne.
    externes_a_retirer: tuple[str, ...] = ()


#: Table curee. Chaque entree a ete confrontee a la source citee.
CORRECTIONS: tuple[Correction, ...] = (
    Correction(
        item_id="7033f440", titre="Désiré",
        createur_faux="Kyan Khojandi", createur="Albert Dupontel",
        # AlloCiné, fiche deja liee dans le corpus : « Désiré - Court Métrage »,
        # « réalisé par Albert Dupontel ». La citation de l'episode est
        # d'ailleurs de Dupontel parlant de son propre film.
        preuve="https://www.allocine.fr/film/fichefilm_gen_cfilm=58283.html",
        # Le compte Instagram etait celui de l'animateur, pas du realisateur.
        externes_a_retirer=("instagram",),
    ),
    Correction(
        item_id="278b0017", titre="Faire kiffer les anges",
        createur_faux="Arte", createur="Jean-Pierre Thorn", annee=1997,
        # Wikipedia FR : « documentaire français réalisé par Jean-Pierre Thorn
        # et sorti en 1997 ». Arte l'a diffuse, ne l'a pas realise — et
        # l'annee etait fausse d'un an.
        preuve="https://fr.wikipedia.org/wiki/Faire_kiffer_les_anges",
    ),
    Correction(
        item_id="20b8ed89", titre="Voulez-vous rire avec moi ce soir",
        createur_faux="Netflix", createur="Yacine Belhousse",
        # TMDB 498273, credits : Director = Yacine Belhousse. Netflix est le
        # diffuseur. Un item jumeau (29890e6e) portait deja le bon nom.
        preuve="https://www.themoviedb.org/movie/498273",
    ),
)


def _ecrire(chemin: Path, doc: dict[str, Any]) -> None:
    chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def _corriger_document(doc: dict[str, Any], correction: Correction) -> list[str]:
    """Applique une correction a un document. Renvoie les champs touches."""
    touches: list[str] = []
    if doc.get("creator") == correction.createur_faux:
        doc["creator"] = correction.createur
        touches.append("creator")
    if correction.annee is not None and doc.get("year") not in (None, correction.annee):
        doc["year"] = correction.annee
        touches.append("year")
    externes = doc.get("externalIds")
    if isinstance(externes, dict):
        for cle in correction.externes_a_retirer:
            if cle in externes:
                del externes[cle]
                touches.append(f"externalIds.{cle}")
    return touches


def executer(*, apply: bool) -> dict[str, Any]:
    """Corrige items et recos. Renvoie un rapport."""
    par_id: dict[str, Correction] = {c.item_id: c for c in CORRECTIONS}
    # Les recos ne portent pas d'itemId : on les rattache par titre, ce qui
    # suffit ici, ces trois titres etant sans homonyme dans le corpus.
    par_titre = {c.titre.strip().lower(): c for c in CORRECTIONS}

    rapport = {"items": 0, "recos": 0, "champs": []}
    for chemin in sorted(common.ITEMS_DIR.rglob("*.json")):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        correction = par_id.get(doc.get("id", ""))
        if correction is None:
            continue
        touches = _corriger_document(doc, correction)
        if not touches:
            continue
        log.info("item %s « %s » : %s -> %s (%s)", correction.item_id,
                 correction.titre, correction.createur_faux,
                 correction.createur, ", ".join(touches))
        rapport["items"] += 1
        rapport["champs"].extend(touches)
        if apply:
            _ecrire(chemin, doc)

    for chemin in sorted(common.RECOS_DIR.rglob("*.json")):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # Une reco ecartee ne s'affiche nulle part ; la corriger brouillerait
        # la trace de ce qui a ete ecarte.
        if doc.get("status") == "discarded":
            continue
        correction = par_titre.get((doc.get("title") or "").strip().lower())
        if correction is None:
            continue
        touches = _corriger_document(doc, correction)
        if not touches:
            continue
        log.info("reco %s « %s » : %s", doc.get("id"), correction.titre,
                 ", ".join(touches))
        rapport["recos"] += 1
        if apply:
            _ecrire(chemin, doc)
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Corrige des attributions fautives verifiees une par une "
                    "(un diffuseur ou un animateur a la place de l'auteur).")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(apply=args.apply)
    log.info("%d item(s) et %d reco(s) corrige(s)",
             rapport["items"], rapport["recos"])
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
