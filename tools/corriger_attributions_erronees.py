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

LES TITRES AUSSI, DEPUIS L'ARBITRAGE DU 2026-08-19
--------------------------------------------------
Renommer une oeuvre change son identite affichee et peut casser des
rapprochements : cela demandait un arbitrage, obtenu depuis. Deux graphies
issues du transcript sont corrigees — « Shage » pour Shaga, « Dailyo » pour
Daylio.

Le rattachement des recos se fait par l'ANCIEN titre : c'est celui qu'elles
portent encore au moment ou la passe s'execute.

CE QUI N'EST PAS TRAITE ICI
---------------------------
Les doublons d'items, qui relevent de `fusionner_doublons_cures.py`.
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
    preuve: str
    createur_faux: str | None = None
    createur: str | None = None
    annee: int | None = None
    #: Identifiants externes a retirer : ils designent la mauvaise personne.
    externes_a_retirer: tuple[str, ...] = ()
    #: Graphie corrigee du titre. Le rattachement reste sur `titre`, l'ancien.
    titre_corrige: str | None = None
    #: URLs a retirer : elles menent a une autre oeuvre.
    liens_a_retirer: tuple[str, ...] = ()
    #: Retire le champ `creator` au lieu de le remplacer. Sert quand la
    #: valeur est fausse et qu'aucune attribution sure ne peut la remplacer.
    retirer_createur: bool = False


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
    Correction(
        item_id="227bf692", titre="Shage", titre_corrige="Shaga",
        # Graphie du transcript. La chaine du corpus est « PLANET SHAGA »
        # (UCPnxhyAxViN6eEXglzsEiww, verifiee par yt-dlp) : c'est bien Shaga.
        preuve="https://www.youtube.com/@planetshaga",
    ),
    Correction(
        item_id="0cd44179", titre="Dailyo", titre_corrige="Daylio",
        # Graphie du transcript. L'App Store la nomme « Daylio: Journal
        # intime, Humeur », editeur Relaxio s.r.o. La reco l'ecrivait deja
        # correctement.
        preuve="https://apps.apple.com/fr/app/daylio-journal-intime-humeur/id1194023242",
    ),
    Correction(
        item_id="e9d58ce6", titre="Mister Mystère",
        # Le lien Deezer pointait `album/711471` — un SINGLE de 2010, une
        # piste, verifie par l'API. L'album de -M- est de 2009 et compte 19
        # titres ; il n'existe pas sur Deezer sous ce nom, alors que le lien
        # Apple Music deja pose (1442791256) est le bon. Un lien qui mene a
        # une autre oeuvre vaut moins que pas de lien.
        preuve="https://api.deezer.com/album/711471",
        liens_a_retirer=("https://www.deezer.com/album/711471",),
    ),
    Correction(
        item_id="6426d70c", titre="Balade Mentale",
        createur_faux="Christophe Pauly", createur="Théo Drieu, Kévin Fauvre",
        # Signale a la relecture du 2026-08-19 : « ce n'est pas le createur de
        # BM ». Wikipedia FR : « chaine Youtube francaise de vulgarisation
        # scientifique creee en 2015 par Theo Drieu et Kevin Fauvre ».
        # Christophe Pauly est un journaliste et auteur de science-fiction ne
        # en 1964 — quelqu'un d'autre. Le compte Instagram qui l'accompagnait
        # etait le sien, pas celui de la chaine.
        preuve="https://fr.wikipedia.org/wiki/Balade_Mentale",
        liens_a_retirer=("https://www.instagram.com/christophepauly.tv/",),
    ),
    Correction(
        item_id="86eb4e90", titre="LOL",
        createur_faux="Paul de Saint Sernin", retirer_createur=True,
        # Une reco creditait « LOL » a Paul de Saint Sernin, qui est celui qui
        # la RECOMMANDE dans l'episode — confusion classique de l'extraction.
        # Aucune attribution sure ne la remplace : l'arbitrage du corpus
        # (`corrections_reco_anomalies.py`, ubm-2892) dit de laisser le champ
        # vide plutot que de substituer une attribution douteuse.
        preuve="https://www.themoviedb.org/tv/122228",
    ),
)


def _ecrire(chemin: Path, doc: dict[str, Any]) -> None:
    chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def _corriger_document(doc: dict[str, Any], correction: Correction) -> list[str]:
    """Applique une correction a un document. Renvoie les champs touches."""
    touches: list[str] = []
    if correction.retirer_createur and doc.get("creator") == correction.createur_faux:
        del doc["creator"]
        touches.append("creator")
    elif correction.createur is not None and doc.get("creator") == correction.createur_faux:
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
    if correction.titre_corrige and doc.get("title") != correction.titre_corrige:
        doc["title"] = correction.titre_corrige
        touches.append("title")
    if correction.liens_a_retirer:
        avant = doc.get("links") or []
        garde = [lien for lien in avant
                 if not (isinstance(lien, dict)
                         and lien.get("url") in correction.liens_a_retirer)]
        if len(garde) != len(avant):
            doc["links"] = garde
            touches.append("links")
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
        # Le journal dit ce qui bouge vraiment : une entree peut ne corriger
        # qu'un titre ou qu'un lien, sans toucher au createur.
        quoi = (f"{correction.createur_faux} -> {correction.createur}"
                if correction.createur else ", ".join(touches))
        log.info("item %s « %s » : %s", correction.item_id, correction.titre, quoi)
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
