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
    #: Graphie du createur a imposer. Les fiches en double portent souvent
    #: deux graphies, dont l'une vient du transcript et l'autre d'une source.
    createur: str | None = None
    #: Cles d'`externalIds` que le perdant NE DOIT PAS transmettre. Sert quand
    #: l'identifiant designe autre chose que l'oeuvre — le compte personnel
    #: d'un co-createur, par exemple.
    externes_a_ne_pas_reprendre: tuple[str, ...] = ()
    #: Titres que le groupe admet EN PLUS de celui du survivant. Sans cette
    #: liste, le garde-fou des titres divergents bloque — et il a raison de
    #: bloquer par defaut : deux titres differents signalent presque toujours
    #: deux oeuvres. L'exception se declare, elle ne se devine pas.
    titres_alternatifs: tuple[str, ...] = ()
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
        survivant="1c5928e1", perdants=("02a01b94",),
        titre="Pulsions",
        # Le spectacle de Kyan Khojandi existait aussi au singulier, avec une
        # mention publiee et un seul lien la ou l'autre fiche en porte cinq.
        # Meme lien YouTube vers le spectacle integral des deux cotes.
        raison="« Pulsion » au singulier, meme spectacle",
        types=("spectacle", "video"),
        createur="Kyan Khojandi, Navo",
        titres_alternatifs=("Pulsion",),
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

    # --- Vingt-deux doublons FRANCS (2026-08-19) --------------------------
    # Meme titre, meme type, createurs compatibles : il n'y a rien a
    # arbitrer, et l'editeur a demande de les fusionner sans le deranger.
    # Le survivant est la fiche la mieux renseignee — createur, identifiants
    # externes, liens manuels, annee — et non la plus citee : une fiche
    # pauvre tres citee reste pauvre.
    #
    # Aucun `types` n'est impose : les deux fiches s'accordent deja.
    Groupe(
        survivant="7f74a9dd", perdants=("b35c18df",),
        titre="Adel Fugazi",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="372c8ea6", perdants=("2bae2669",),
        titre="Barbès Comedy Club",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="4d802505", perdants=("3d447d4e",),
        titre="Comment c'est loin",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="154970ac", perdants=("f70ffecf",),
        titre="Euphoria",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="7e2f2669", perdants=("f1d88049",),
        titre="Floodcast",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="fa52ae22", perdants=("fd6f56ee",),
        titre="I Will Survive",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="e144b9b9", perdants=("909ec4b7",),
        titre="L'Effondrement",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="de1ed6c0", perdants=("97aa4894",),
        titre="Le Visiteur du futur",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="c14574a7", perdants=("706a7439",),
        titre="Les mecs que je veux ken",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="f7d575cd", perdants=("043f9f4e",),
        titre="Les Nouveaux Sauvages",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="348facf5", perdants=("34705998",),
        titre="Les Pieds sur Terre",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="27f69c55", perdants=("27745c51",),
        titre="Les Quatre Accords Toltèques",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="b600d479", perdants=("e12a58bf",),
        titre="Loki",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="3476d875", perdants=("ad4eac0b",),
        titre="Los años nuevos",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="765a0b3a", perdants=("c8c7aa04",),
        titre="Lève-toi et tombe",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="7d95093f", perdants=("a167aa0d",),
        titre="Message Personnel",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="0ce04c0f", perdants=("792a8bb7",),
        titre="Pluribus",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="7d06a413", perdants=("0b4a4b06",),
        titre="Ricky Gervais",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="f5c1e93f", perdants=("237187fc",),
        titre="Sugar Sammy",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="235e92d1", perdants=("877b2d63",),
        titre="The Great Review",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="9bd83eb2", perdants=("d140d440",),
        titre="Théo Babac",
        raison="doublon franc : meme type, createurs compatibles",
    ),
    Groupe(
        survivant="45706764", perdants=("8be1a426",),
        titre="White Fire",
        raison="doublon franc : meme type, createurs compatibles",
    ),

    # --- Seize fusions ARBITREES (2026-08-19) ----------------------------
    # Trois agents ont examine ces groupes un par un et rendu un verdict
    # source a l'appui ; les dix-sept sources ont ete ouvertes et verifiees,
    # puis l'editeur a valide l'ensemble.
    #
    # Elles se distinguent des doublons francs ci-dessus par ce qui les
    # rendait invisibles au groupement automatique : deux graphies de
    # createur, dont l'une venait du transcript.
    Groupe(
        survivant="f2b90f79", perdants=("ed31790d",),
        titre="Continue tu m'intéresses",
        # Même podcast : les deux fiches portent exactement les mêmes liens (shows.acast.com/continue-tu-minteresses, Apple id1812415752, Deezer 1001857631, Spo
        # Source : https://itunes.apple.com/lookup?id=1812415752&country=fr
        raison="arbitre le 2026-08-19, source verifiee",
        types=("podcast",),
        createur="Patrick Baud",
    ),
    Groupe(
        survivant="30fe030e", perdants=("c3e6abbd", "eb960ae6"),
        titre="Des trains à travers la plaine",
        # Un seul et même podcast : les trois fiches portent exactement les mêmes liens (shows.acast.com/des-trains-a-travers-la-plaine, Apple id1549461850, Spo
        # Source : https://shows.acast.com/des-trains-a-travers-la-plaine
        raison="arbitre le 2026-08-19, source verifiee",
        types=("podcast",),
        createur="Ambroise Carminati, Baptiste Pignon, Nicolas Roux",
    ),
    Groupe(
        survivant="1c0535f8", perdants=("02664ef8",),
        titre="Gus",
        # Même œuvre : les deux fiches pointent vers la même vidéo (GgcJxj0yugM) et la même chaîne (@JÉRÉMIEDETHELOT). yt-dlp sur cette vidéo renvoie chaîne « J
        # Source : https://www.senscritique.com/serie/GUS/38953092
        raison="arbitre le 2026-08-19, source verifiee",
        types=("serie",),
        createur="Jérémie Dethelot",
    ),
    Groupe(
        survivant="f395a970", perdants=("1747634f",),
        titre="Invisible",
        # Même œuvre : le programme Canal+ « Invisible » de Clément Cotentin. La page Apple TV du lien de la fiche serie donne le synopsis « Pour rendre visible
        # Source : https://tv.apple.com/fr/show/invisible/umc.cmc.69qq448caxln83g9jadkqsaus
        raison="arbitre le 2026-08-19, source verifiee",
        types=("serie",),
        createur="Clément Cotentin",
    ),
    Groupe(
        survivant="82a4d2a6", perdants=("124d9468",),
        titre="Jour de pluie",
        # Même œuvre : les deux fiches portent le même externalId Instagram « pierrehillairet_ » et les mêmes liens (billetreduc 408073, theatredumarais.fr). La
        # Source : https://www.billetreduc.com/spectacle/pierre-hillairet-dans-jour-de-pluie-408073
        raison="arbitre le 2026-08-19, source verifiee",
        types=("spectacle",),
        createur="Pierre Hillairet",
    ),
    Groupe(
        survivant="334b7420", perdants=("15f5edf7",),
        titre="Julien Santini",
        # Même humoriste : les deux fiches portent le même nom et exactement les mêmes quatre liens (santinicomedy.com, gaite.com, ngproductions.fr, fnacspectac
        # Source : https://gaite.com/spectacles/julien-santini/
        raison="arbitre le 2026-08-19, source verifiee",
        types=("artiste", "spectacle"),
        createur="Julien Santini",
    ),
    Groupe(
        survivant="3de6f4e2", perdants=("2942b178",),
        titre="Kheiron",
        # Les deux fiches désignent la même personne : Manouchehr Tabib, dit Kheiron, humoriste et réalisateur franco-iranien. Elles pointent toutes deux vers l
        # Source : https://fr.wikipedia.org/wiki/Kheiron
        raison="arbitre le 2026-08-19, source verifiee",
        types=("artiste", "spectacle"),
        createur="Kheiron",
    ),
    Groupe(
        survivant="27b7d50a", perdants=("95958aeb",),
        titre="L'épreuve du feu",
        # Un seul film, pas deux : les deux fiches portent exactement les mêmes trois liens (sooner.fr/films/l-epreuve-du-feu-1, AlloCiné 1000001690, JustWatch
        # Source : https://www.allocine.fr/film/fichefilm_gen_cfilm=1000001690.html
        raison="arbitre le 2026-08-19, source verifiee",
        types=("film",),
        createur="Aurélien Peyre",
    ),
    Groupe(
        survivant="8bd96ef1", perdants=("9daec9c1",),
        titre="La Course des géants",
        # Même pièce : mêmes deux liens sur les deux fiches (Théâtre des Béliers Parisiens et Théâtre de la Renaissance). La page du Théâtre des Béliers Parisie
        # Source : https://www.theatredesbeliersparisiens.com/spectacle/la-course-des-geants-tournee/
        raison="arbitre le 2026-08-19, source verifiee",
        types=("spectacle",),
        createur="Mélody Mourey",
    ),
    Groupe(
        survivant="1bf77f8a", perdants=("452a3c98",),
        titre="Le Bureau des Légendes",
        # Même série, sans ambiguïté : les quatre mentions parlent de la série française de Canal+ (« la meilleure série française au monde », « qui est sur MyC
        # Source : https://fr.wikipedia.org/wiki/Le_Bureau_des_l%C3%A9gendes
        raison="arbitre le 2026-08-19, source verifiee",
        types=("serie",),
        createur="Éric Rochant",
    ),
    Groupe(
        survivant="5c481b82", perdants=("1a693d09",),
        titre="Le Trône des Frogz",
        # Même œuvre : les deux fiches portent les mêmes six liens, dont le même IMDb (tt5485592) et le même TMDB (tv/81160). La page TMDB ouverte crédite « Yac
        # Source : https://www.themoviedb.org/tv/81160
        raison="arbitre le 2026-08-19, source verifiee",
        types=("serie", "video"),
        createur="Yacine Belhousse",
    ),
    Groupe(
        survivant="fdb364ab", perdants=("de1dd4f5",),
        titre="Louis Chappey",
        # Même personne : un seul humoriste porte ce nom, et les deux mentions viennent du même milieu stand-up (Jason Brokerss ubm-2878, Rémi Boyes ubm-3047 «
        # Source : https://www.youtube.com/watch?v=gSUdYDNzJLk
        raison="arbitre le 2026-08-19, source verifiee",
        types=("artiste",),
        createur="Louis Chappey",
    ),
    Groupe(
        survivant="9e2e879d", perdants=("7210e327",),
        titre="Pomme",
        # Une seule œuvre : l'artiste. Les deux fiches portent rigoureusement les mêmes liens, tous des liens d'artiste et non d'œuvre (Deezer artist/5382747 —
        # Source : https://api.deezer.com/artist/5382747
        raison="arbitre le 2026-08-19, source verifiee",
        types=("artiste", "musique", "spectacle"),
        createur="Pomme",
    ),
    Groupe(
        survivant="1c5928e1", perdants=("7e85327e",),
        titre="Pulsions",
        # Même œuvre, sans le moindre doute : titre, types, externalIds (instagram kyankhojandi) et les cinq liens sont rigoureusement identiques sur les deux f
        # Source : https://fr.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&format=json&titles=Kyan%20Khojandi
        raison="arbitre le 2026-08-19, source verifiee",
        types=("spectacle", "video"),
        createur="Kyan Khojandi, Navo",
    ),
    Groupe(
        survivant="af15df89", perdants=("85902a09",),
        titre="Validé",
        # Même série Canal+ : les deux fiches portent les mêmes identifiants d'œuvre (AlloCiné 24293, IMDb tt11537880, TMDB 90816, Netflix 82157057). L'article
        # Source : https://fr.wikipedia.org/wiki/Valid%C3%A9
        raison="arbitre le 2026-08-19, source verifiee",
        types=("serie",),
        createur="Franck Gastambide",
        # `85902a09` porte `instagram: xavier.lacaille` — le compte personnel
        # d'un des quatre co-createurs, pas celui de la serie. Sans cette
        # exclusion, la fusion le ferait migrer sur la fiche survivante.
        externes_a_ne_pas_reprendre=("instagram",),
    ),
    Groupe(
        survivant="815746f1", perdants=("9e67d5ae",),
        titre="La Zone d'intérêt",
        # Deux fiches pour le film de Jonathan Glazer, l'une sous son
        # titre francais, l'autre sous l'anglais. Leurs deux mentions
        # pointaient le meme instant (00:31:44) et la meme phrase.
        # Source : https://www.themoviedb.org/movie/467244
        raison="titre francais et titre anglais de la meme oeuvre",
        types=("film",),
        createur="Jonathan Glazer",
        titres_alternatifs=("The Zone of Interest",),
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
        admis = {(t or "").strip().lower() for t in groupe.titres_alternatifs}
        titres = {(d.get("title") or "").strip().lower()
                  for d in [survivant, *docs_perdants]} - admis
        if len(titres) > 1:
            # Un titre different signale que la table ne decrit plus le
            # corpus : mieux vaut s'arreter que fusionner deux oeuvres.
            rapport["refus"].append(
                f"{groupe.titre} : titres divergents {sorted(titres)}")
            continue

        fusionner(survivant, docs_perdants, groupe.a_arbitrer)
        if groupe.types:
            survivant["types"] = list(groupe.types)
        if groupe.createur:
            survivant["creator"] = groupe.createur
        for cle in groupe.externes_a_ne_pas_reprendre:
            externes = survivant.get("externalIds")
            if isinstance(externes, dict) and cle in externes:
                del externes[cle]

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
