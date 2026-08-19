"""
fusionner_doublons_cures.py — fusionner ce que l'automatisme ne voit pas.

POURQUOI UN SECOND OUTIL DE FUSION
----------------------------------
`fusion_items_doublons.py` groupe les fiches par identifiant TMDB, ou par
titre ET createur identiques. Ces garde-fous sont bons : ils evitent de
confondre deux oeuvres homonymes.

Mais ils laissent passer un cas frequent : deux fiches du meme titre dont
l'une est NUE — ni createur, ni identifiant externe. L'outil ne peut pas
savoir si c'est la meme oeuvre ; un humain, si.

Releve a la relecture du 2026-08-19 : « Balade Mentale (3 fiches), Orelsan
(3 fiches dont une "Aurelsan"), Visionnaire », auxquelles s'ajoutent LOL,
Fabien Olicard et Voulez-vous rire, trouves en verifiant les premiers.

CHAQUE GROUPE A ETE VERIFIE A LA MAIN
-------------------------------------
La table dit quelle fiche survit et lesquelles disparaissent, avec la raison.
On garde celle qui porte le plus d'information — createur, identifiants
externes — et non la plus citee : une fiche pauvre tres citee reste pauvre.

CE QUI EST REUTILISE
--------------------
`fusionner()` de l'outil existant, qui verse dans le survivant ce que les
perdants ont en plus sans jamais l'ecraser. Reecrire cette logique aurait
produit deux comportements a maintenir.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common
from fusion_items_doublons import fusionner

log = logging.getLogger("doublons_cures")


@dataclass(frozen=True)
class Groupe:
    """Un groupe de fiches a fusionner, et pourquoi."""
    survivant: str
    perdants: tuple[str, ...]
    titre: str
    raison: str
    #: Types a poser sur le survivant apres fusion, si les fiches divergeaient.
    types: tuple[str, ...] = ()
    a_arbitrer: list[str] = field(default_factory=list)


#: Table curee. Le survivant est la fiche la mieux renseignee.
GROUPES: tuple[Groupe, ...] = (
    Groupe(
        survivant="6426d70c", perdants=("80c61fe8", "fda1b4a0"),
        titre="Balade Mentale",
        # Seule 6426d70c porte le createur (Christophe Pauly) et un compte
        # Instagram. Les deux autres sont nues. C'est une chaine YouTube de
        # vulgarisation : ni un podcast, ni une video isolee.
        raison="trois fiches pour une chaine YouTube ; une seule renseignee",
        types=("chaine",),
    ),
    Groupe(
        survivant="4b128080", perdants=("9e26515a",),
        titre="Orelsan",
        # 4b128080 porte le createur et l'Instagram, et concentre trois des
        # quatre mentions. Les deux fiches « Aurelsan » (01ce0eb9, b19f79c6)
        # n'ont AUCUNE mention publiee : elles ne s'affichent nulle part et
        # sortent du perimetre.
        raison="deux fiches pour le meme artiste ; une seule renseignee",
        types=("artiste", "musique"),
    ),
    Groupe(
        survivant="10df5ed6", perdants=("fc8bd564",),
        titre="Fabien Olicard",
        # 10df5ed6 porte le createur, l'Instagram et le TikTok.
        raison="deux fiches pour la meme personne ; une seule renseignee",
        types=("artiste", "chaine"),
    ),
    Groupe(
        survivant="86eb4e90", perdants=("dd668978", "9d9cf893"),
        titre="LOL",
        # Trois fiches pour « LOL : Qui rit, sort ! », le programme Prime
        # Video. Le survivant porte le diffuseur ; les types divergeaient
        # (`video` / `serie,spectacle`) et la regle du 2026-08-19 tranche :
        # un programme de television non scenarise est une `video`.
        raison="trois fiches pour le meme programme Prime Video",
        types=("video",),
    ),
    Groupe(
        survivant="20b8ed89", perdants=("29890e6e",),
        titre="Voulez-vous rire avec moi ce soir",
        # Le survivant n'est pas celui qu'on croit. 29890e6e semblait mieux
        # renseigne, mais il ecrit « Yacine Bellous » ; 20b8ed89 porte
        # « Yacine Belhousse », la graphie confirmee par TMDB (fiche 498273)
        # et posee par `corriger_attributions_erronees.py`.
        raison="deux fiches pour le meme spectacle filme ; graphies du "
               "realisateur divergentes",
        types=("film",),
    ),
    Groupe(
        survivant="c1be5cf1", perdants=("50b3cd38",),
        titre="Fouloscopie",
        # Arbitre a la relecture du 2026-08-19. Mehdi Moussaid tient une
        # chaine YouTube de vulgarisation sur les foules ET a publie un livre
        # du meme nom ; les recos pointent aussi des videos precises. Les
        # trois types sont donc vrais a la fois — « il y a bien 3 types tres
        # differents, l'auteur est prolifique ».
        #
        # `podcast`, porte par la fiche perdante, sort : rien dans le corpus
        # ne rattache Fouloscopie a un podcast.
        raison="deux fiches pour une chaine, un livre et des videos",
        types=("chaine", "livre", "video"),
    ),
)


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


def executer(groupes: Sequence[Groupe], *, apply: bool) -> dict[str, Any]:
    """Fusionne les groupes de la table. Renvoie un rapport."""
    items = _charger(common.ITEMS_DIR)
    mentions = _charger(common.MENTIONS_DIR)

    rapport: dict[str, Any] = {"fusions": 0, "supprimes": 0,
                               "mentions_reportees": 0, "refus": []}
    for groupe in groupes:
        if groupe.survivant not in items:
            rapport["refus"].append(
                f"{groupe.titre} : survivant {groupe.survivant} introuvable")
            continue
        presents = [p for p in groupe.perdants if p in items]
        if not presents:
            # Deja fusionne lors d'une passe precedente.
            continue

        _, survivant = items[groupe.survivant]
        docs_perdants = [items[p][1] for p in presents]
        titres = {(d.get("title") or "").strip().lower()
                  for d in [survivant, *docs_perdants]}
        if len(titres) > 1:
            # Un titre different signale que la table ne decrit plus le
            # corpus : mieux vaut s'arreter que fusionner deux oeuvres.
            rapport["refus"].append(
                f"{groupe.titre} : titres divergents {sorted(titres)}")
            continue

        fusionner(survivant, docs_perdants, groupe.a_arbitrer)
        if groupe.types:
            survivant["types"] = list(groupe.types)

        for perdant in presents:
            for chemin_m, mention in mentions.values():
                if mention.get("itemId") != perdant:
                    continue
                mention["itemId"] = groupe.survivant
                rapport["mentions_reportees"] += 1
                if apply:
                    _ecrire(chemin_m, mention)

        log.info("%s : %s <- %s (%d perdant·s)", groupe.titre,
                 groupe.survivant, ", ".join(presents), len(presents))
        rapport["fusions"] += 1
        rapport["supprimes"] += len(presents)
        if apply:
            _ecrire(items[groupe.survivant][0], survivant)
            for perdant in presents:
                items[perdant][0].unlink()
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fusionne des doublons d'items verifies a la main, que "
                    "le groupement automatique ne peut pas reconnaitre.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(GROUPES, apply=args.apply)
    log.info("%d fusion(s), %d item(s) supprime(s), %d mention(s) reportee(s)",
             rapport["fusions"], rapport["supprimes"],
             rapport["mentions_reportees"])
    for refus in rapport["refus"]:
        log.warning("REFUS %s", refus)
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
