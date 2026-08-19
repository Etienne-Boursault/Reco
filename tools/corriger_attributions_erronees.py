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

COMMENT UNE RECO EST RATTACHEE A SA CORRECTION
----------------------------------------------
Par son OEUVRE, et par elle seule : `mention.itemId` designe la fiche, et
mention et reco partagent leur identifiant.

La premiere version rattachait par TITRE, et ca s'est vu tout de suite : deux
fiches distinctes s'appelaient « Vincent Delerm » — l'artiste, et la bande
originale d'un de ses films. Renommer la seconde a renomme la reco de la
premiere.

Le titre a d'abord ete garde comme repli, pour les recos qu'aucune mention ne
relie ; un test a montre que le repli reproduisait exactement le meme defaut.
Il est parti. Une reco sans mention publiee ne s'affiche nulle part : ne pas
la corriger ne coute rien.

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
    #: La valeur fautive attendue. Plusieurs quand la fiche et ses recos ne
    #: se trompent pas de la meme facon — « LOL » creditait la plateforme
    #: cote oeuvre et le recommandeur cote reco.
    createur_faux: str | tuple[str | None, ...] | None = None
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
    #: Liens a POSER, en fin de liste, s'ils n'y sont pas deja.
    liens_a_ajouter: tuple[dict[str, str], ...] = ()


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
        item_id="41d34be6", titre="Les grands classiques d'Hitchcock",
        # « Je prefererais tout de meme trouver des oeuvres disponibles sur
        # differentes plateformes a donner aux utilisateurs » (2026-08-19).
        # L'oeuvre designe un CORPUS : aucune fiche unique n'existe, mais on
        # peut ouvrir la filmographie et deux facons de la regarder.
        #
        # La fiche AlloCine n'y est pas : l'identifiant 1093, qu'on aurait pu
        # croire le sien, est celui de Raymond Leblanc. Verifie avant de
        # l'ecarter.
        preuve="https://www.themoviedb.org/person/2636-alfred-hitchcock",
        liens_a_ajouter=(
            {"kind": "info", "ethics": "neutral",
             "label": "Filmographie (TMDB)",
             "url": "https://www.themoviedb.org/person/2636-alfred-hitchcock"},
            {"kind": "streaming", "ethics": "neutral",
             "label": "Où regarder (JustWatch)",
             "url": "https://www.justwatch.com/fr/recherche?q=Alfred+Hitchcock"},
            {"kind": "streaming", "ethics": "indie", "label": "arte.tv",
             "url": "https://www.arte.tv/fr/search/?q=hitchcock"},
        ),
    ),
    Correction(
        item_id="f33795ad", titre="Les futurs lointains, un voyage en direction de l'éternité",
        # Meme erreur que sur « Balade Mentale », dont cette video est issue :
        # le compte Instagram est celui de Christophe Pauly, un journaliste
        # sans rapport avec la chaine de Theo Drieu et Kevin Fauvre.
        preuve="https://fr.wikipedia.org/wiki/Balade_Mentale",
        externes_a_retirer=("instagram",),
        liens_a_retirer=("https://www.instagram.com/christophepauly.tv/",),
    ),
    Correction(
        item_id="1c5928e1", titre="Pulsions",
        # Navo est le nom de scene de Bruno Muschio. Les deux sont exacts,
        # mais le site le nomme « Navo » partout ailleurs — un lecteur ne
        # reconnaitrait pas « Bruno Muschio ». Arbitre le 2026-08-19 :
        # « tu peux ajouter Navo en tant que co-createur pour toutes les
        # cartes ».
        createur_faux=("Kyan Khojandi", "Kyan Khojandi, Bruno Muschio"),
        createur="Kyan Khojandi, Navo",
        preuve="https://fr.wikipedia.org/wiki/Kyan_Khojandi",
    ),
    Correction(
        item_id="7e2f2669", titre="FloodCast",
        # « Flaubert, Adrien Meignel » est ce que la transcription a entendu.
        # Le podcast est de Florent Bernard et Adrien Menielle, ce que la page
        # officielle et les autres recos du corpus disent deja.
        createur_faux="Flaubert, Adrien Meignel",
        createur="Florent Bernard, Adrien Ménielle",
        preuve="https://fr.wikipedia.org/wiki/Florent_Bernard",
    ),
    Correction(
        item_id="f2b90f79", titre="Continue tu m'intéresses",
        # « Patrick » tronque le nom ; iTunes (id1812415752) donne
        # « Patrick Baud », deja retenu lors de l'arbitrage des doublons.
        createur_faux="Patrick", createur="Patrick Baud",
        preuve="https://itunes.apple.com/lookup?id=1812415752&country=fr",
    ),
    Correction(
        item_id="1c0535f8", titre="Gus",
        # SensCritique credite « Jeremie Dethelot et Haroun Saifi » (2019) ;
        # le co-auteur manquait aux deux fiches fusionnees.
        # Les deux graphies sont visees : la fiche portait « Jeremie
        # Dethelot », une reco portait encore « Jeremy Detlo », phonetique.
        createur_faux=("Jérémie Dethelot", "Jérémy Detlo"),
        createur="Jérémie Dethelot, Haroun Saifi",
        preuve="https://www.senscritique.com/serie/GUS/38953092",
    ),
    Correction(
        item_id="5c481b82", titre="Le Trône des Frogz",
        # La fiche a herite du compte de l'AUTEUR lors de la fusion. Celui du
        # studio producteur s'y ajoute : `externalIds.instagram` n'acceptant
        # qu'un handle, le second passe par `customLinks`.
        #
        # Le handle vient de la description des videos de la chaine Golden
        # Moustache elle-meme — @goldenoff, et non @goldenmoustache comme on
        # l'aurait suppose. Instagram repondant 200 a n'importe quel profil,
        # une verification par code HTTP n'aurait rien prouve.
        preuve="https://www.youtube.com/@GoldenMoustache",
        liens_a_ajouter=(
            {"kind": "social", "ethics": "neutral",
             "label": "Instagram — Golden Moustache",
             "url": "https://www.instagram.com/goldenoff/"},
        ),
    ),
    Correction(
        item_id="c054d35a", titre="Vincent Delerm",
        titre_corrige="Je ne sais pas si c'est tout le monde (Bande originale du film)",
        # Cette fiche n'est pas l'artiste mais un ALBUM : la citation dit « la
        # BO du film qu'il a fait », et ses liens pointent la bande originale.
        # Portant le nom de l'artiste, elle faisait un faux doublon avec la
        # vraie fiche « Vincent Delerm ». Titre exact confirme par Deezer
        # (album 122899792). Le createur perdait aussi un « e » de trop.
        createur_faux="Vincent Delerme", createur="Vincent Delerm",
        preuve="https://api.deezer.com/album/122899792",
    ),
    Correction(
        item_id="27b7d50a", titre="L'épreuve du feu",
        titre_corrige="L'Épreuve du feu",
        # La fiche disparue dans la fusion portait la majuscule, celle qui
        # survit ne l'avait pas. AlloCine ecrit « L'Épreuve du feu ».
        preuve="https://www.allocine.fr/film/fichefilm_gen_cfilm=1000001690.html",
    ),
    Correction(
        item_id="86eb4e90", titre="LOL",
        # Deux erreurs differentes pour la meme oeuvre : la FICHE creditait la
        # plateforme de diffusion, une RECO creditait celui qui la recommande.
        # Trois valeurs fautives se sont succede : la plateforme de diffusion
        # cote fiche, celui qui la recommande cote reco, puis « Philippe
        # Lacheau » — que j'avais pose faute de mieux, Wikipedia le donnant
        # comme PRESENTATEUR. L'editeur a tranche le 2026-08-19 : presenter
        # n'est pas creer, et TMDB ne renseigne aucun `created_by` pour cette
        # fiche. Le champ reste vide.
        createur_faux=("Amazon Prime", "Paul de Saint Sernin",
                       "Philippe Lacheau"),
        retirer_createur=True,
        # Une reco creditait « LOL » a Paul de Saint Sernin, qui est celui qui
        # la RECOMMANDE dans l'episode — confusion classique de l'extraction.
        # L'autre carte n'avait aucun createur : « il n'y a pas le createur »
        # (2026-08-19).
        #
        # Wikipedia FR : « emission francaise de television diffusee sur
        # Amazon Prime Video depuis 2021 et presentee par Philippe Lacheau ».
        # TMDB ne renseigne aucun `created_by` pour cette fiche — le format
        # original est le japonais « Documental » d'Hitoshi Matsumoto. C'est
        # donc le PRESENTATEUR qui est credite, faute de createur identifie,
        # et c'est ce que le public associe a l'emission.
        preuve="https://fr.wikipedia.org/wiki/LOL_:_qui_rit,_sort_!",
    ),
)


def _ecrire(chemin: Path, doc: dict[str, Any]) -> None:
    chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")


def _corriger_document(doc: dict[str, Any], correction: Correction, *,
                       champ_liens: str = "links") -> list[str]:
    """Applique une correction a un document. Renvoie les champs touches.

    `champ_liens` vaut `links` sur une reco et `customLinks` sur une fiche
    d'oeuvre : les deux collections ne portent pas leurs liens de la meme
    facon, et `customLinks` n'accepte que `label`, `url` et `logoUrl`.
    """
    touches: list[str] = []
    faux = correction.createur_faux
    fautifs = (faux,) if isinstance(faux, str) else (faux or ())
    if correction.retirer_createur and doc.get("creator") in fautifs:
        del doc["creator"]
        touches.append("creator")
    elif correction.createur is not None and doc.get("creator") in fautifs:
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
    if correction.liens_a_ajouter:
        liens = list(doc.get(champ_liens) or [])
        presentes = {lien.get("url") for lien in liens if isinstance(lien, dict)}
        manquants = [
            {"label": lien["label"], "url": lien["url"]}
            if champ_liens == "customLinks" else dict(lien)
            for lien in correction.liens_a_ajouter
            if lien["url"] not in presentes
        ]
        if manquants:
            doc[champ_liens] = [*liens, *manquants]
            touches.append(f"+{len(manquants)} lien(s)")
    if correction.liens_a_retirer:
        avant = doc.get(champ_liens) or []
        garde = [lien for lien in avant
                 if not (isinstance(lien, dict)
                         and lien.get("url") in correction.liens_a_retirer)]
        if len(garde) != len(avant):
            doc[champ_liens] = garde
            touches.append(champ_liens)
    return touches


def _corrections_par_reco() -> dict[str, Correction]:
    """id de reco -> correction, via les mentions publiees de son oeuvre."""
    par_item = {c.item_id: c for c in CORRECTIONS}
    trouvees: dict[str, Correction] = {}
    for chemin in common.MENTIONS_DIR.rglob("*.json"):
        try:
            mention = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        correction = par_item.get(mention.get("itemId", ""))
        if correction is not None and mention.get("id"):
            trouvees[mention["id"]] = correction
    return trouvees


def executer(*, apply: bool) -> dict[str, Any]:
    """Corrige items et recos. Renvoie un rapport."""
    par_id: dict[str, Correction] = {c.item_id: c for c in CORRECTIONS}
    par_reco = _corrections_par_reco()

    rapport = {"items": 0, "recos": 0, "champs": []}
    for chemin in sorted(common.ITEMS_DIR.rglob("*.json")):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        correction = par_id.get(doc.get("id", ""))
        if correction is None:
            continue
        touches = _corriger_document(doc, correction, champ_liens="customLinks")
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
        correction = par_reco.get(doc.get("id", ""))
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
