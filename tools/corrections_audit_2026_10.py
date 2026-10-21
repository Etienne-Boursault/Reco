"""
corrections_audit_2026_10.py — ce qu'un audit exterieur a trouve sur le site.

D'OU VIENNENT CES CAS
---------------------
Un audit du site public (2026-10-20) a releve des fiches fausses : « Salade
grecque » rangee en film et creditee a « Cedric Clapichon », « Jim & Andy »
attribue a Milos Forman, « La Femme de menage » a Marc Levy, des artistes
ranges en « album », des doublons (Joe Rogan, Barbes Comedy Club).

Chaque exemple a ete confirme, puis le releve etendu aux 1093 oeuvres
PUBLIEES — celles qu'une mention validee affiche. Les oeuvres des seules recos
ecartees ne s'affichent nulle part et sortent volontairement du perimetre.

CE QUE FAIT CE SCRIPT, DANS L'ORDRE
-----------------------------------
1. Fusionne neuf paires de fiches qui designent la meme oeuvre, avec le moteur
   de `fusionner_doublons_cures.py` (mentions reportees, perdants supprimes,
   ancien titre garde en alias pour la recherche).
2. Corrige titres, createurs et types avec celui de
   `corriger_attributions_erronees.py`, sur la fiche ET ses recos publiees :
   la carte d'episode lit la reco, la page de l'oeuvre lit la fiche.
3. Ecarte une mention en double.

L'etape 2 retrouve les recos par les mentions ECRITES par l'etape 1 : la
simulation sous-estime donc les recos touchees. Seul `--apply` est complet.

CHAQUE LIGNE A ETE VERIFIEE
---------------------------
Le champ `preuve` porte la source ouverte. Graphies confirmees au passage :
Verino s'appelle Olivier Balestriero (le corpus ecrivait « Balestrier »), Iron
& Wine est Sam Beam (« Sam Bean »), le humoriste s'ecrit Paul Dechavanne.

Faux doublons ecartes apres verification, a ne PAS fusionner : « Happy End »
(un podcast, un album), « Desire » (film) et « Desirer » (livre), « Parasite »
et « Les Parasites », « Soixante » et « Soixante 2 ».
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common
from corriger_attributions_erronees import Correction
from corriger_attributions_erronees import executer as corriger
from fusionner_doublons_cures import Groupe
from fusionner_doublons_cures import executer as fusionner

log = logging.getLogger("audit_2026_10")

GROUPES: tuple[Groupe, ...] = (
    Groupe(
        survivant="0099e3e6", perdants=("0139f55a",),
        titre="The Joe Rogan Experience",
        raison="meme podcast, avec et sans article",
        types=("podcast",), createur="Joe Rogan",
        titres_alternatifs=("Joe Rogan Experience",),
    ),
    Groupe(
        survivant="0c723800", perdants=("a4899870",),
        titre="Bloqués",
        # La fiche au singulier n'a qu'une mention publiee, sans createur.
        raison="« Bloqué » au singulier, meme serie Canal+",
        types=("serie",),
        titres_alternatifs=("Bloqué",),
    ),
    Groupe(
        survivant="26449f22", perdants=("a934f698",),
        titre="Notes pour trop tard",
        raison="« Note » au singulier, meme chanson d'Orelsan",
        types=("musique",), createur="Orelsan",
        titres_alternatifs=("Note pour trop tard",),
    ),
    Groupe(
        # Le survivant porte la bonne graphie ; l'autre fiche, la graphie du
        # transcript, qui reste en alias.
        survivant="2407684e", perdants=("080bcff7",),
        titre="Paul Dechavanne",
        raison="meme humoriste, deux graphies du nom",
        types=("artiste",), createur="Paul Dechavanne",
        titres_alternatifs=("Paul de Chavanne",),
    ),
    Groupe(
        survivant="b0fd5e1f", perdants=("2fbba74c",),
        titre="Outer Wilds",
        raison="meme jeu ; une seule fiche porte le studio",
        types=("jeu",), createur="Mobius Digital",
    ),
    Groupe(
        survivant="7693d750", perdants=("4a82f64f",),
        titre="Vérino",
        raison="meme humoriste, avec et sans accent",
        # Une personne se credite elle-meme (cf. Kheiron, Julien Santini) ;
        # le vrai nom porte par le perdant etait de surcroit mal orthographie.
        types=("artiste", "chaine"), createur="Vérino",
        titres_alternatifs=("Verino",),
    ),
    Groupe(
        survivant="a1994a10", perdants=("53feff25",),
        titre="The Witness",
        # Thekla est le studio ; le jeu est credite a son auteur, Jonathan Blow.
        raison="meme jeu, credite au studio d'un cote, a l'auteur de l'autre",
        types=("jeu",), createur="Jonathan Blow",
    ),
    Groupe(
        survivant="936c2d69", perdants=("9f9ecc30",),
        titre="300 000 ans",
        raison="meme spectacle de Manon Bril, avec et sans espace",
        types=("spectacle",), createur="Manon Bril",
        titres_alternatifs=("300000 ans",),
    ),
    Groupe(
        survivant="372c8ea6", perdants=("ca377608",),
        titre="Barbès Comedy Club",
        raison="meme club, nom francise par le transcript",
        types=("lieu",),
        titres_alternatifs=("Barbès Comédie Club",),
        # Le compte Instagram du perdant est celui de la fondatrice, pas du club.
        externes_a_ne_pas_reprendre=("instagram",),
    ),
)

CORRECTIONS: tuple[Correction, ...] = (
    # --- Createurs faux (releves par l'audit) ------------------------------
    Correction(
        item_id="416701f6", titre="Salade grecque",
        createur_faux="Cédric Clapichon", createur="Cédric Klapisch",
        types=("serie",),
        preuve="https://www.cineserie.com/news/series/series-mania-2023-on-a-vu-la-serie-salade-grecque-signee-cedric-klapisch-5562953/",
    ),
    Correction(
        # Forman a realise « Man on the Moon », dont le documentaire raconte
        # le tournage ; le documentaire lui-meme est de Chris Smith.
        item_id="409fb74b", titre="Jim and Andy",
        titre_corrige="Jim & Andy: The Great Beyond",
        createur_faux="Milos Forman", createur="Chris Smith",
        preuve="https://www.themoviedb.org/movie/469019",
    ),
    Correction(
        item_id="899d03ba", titre="La Femme de Ménage",
        titre_corrige="La Femme de ménage",
        createur_faux="Marc Lévy", createur="Freida McFadden",
        preuve="https://www.jailu.com/la-femme-de-menage/9782290391174",
    ),
    Correction(
        # Jim Carrey en est l'acteur principal et le co-scenariste.
        item_id="ca89875c", titre="Ace Ventura: Pet Detective",
        createur_faux="Jim Carrey", createur="Tom Shadyac",
        preuve="https://en.wikipedia.org/wiki/Ace_Ventura:_Pet_Detective",
    ),
    # --- Une personne rangee en album, ou un album en personne -------------
    Correction(
        item_id="864a1e8a", titre="Zaho de Sagazan",
        types=("artiste", "musique"),
        preuve="https://fr.wikipedia.org/wiki/Zaho_de_Sagazan",
    ),
    Correction(
        item_id="2fd81c0f", titre="Diam's",
        types=("artiste", "musique"),
        preuve="https://www.deezer.com/artist/388",
    ),
    Correction(
        item_id="393468c5", titre="Al'Tarba",
        types=("artiste", "musique"),
        preuve="https://www.deezer.com/artist/201875",
    ),
    Correction(
        item_id="9d76abd5", titre="Iron & Wine",
        createur_faux="Sam Bean", createur="Sam Beam",
        types=("artiste", "musique"),
        preuve="https://en.wikipedia.org/wiki/Iron_%26_Wine",
    ),
    Correction(
        item_id="b1631e09", titre="Civilisation", types=("album",),
        preuve="https://fr.wikipedia.org/wiki/Civilisation_(album)",
    ),
    Correction(
        item_id="d4219229", titre="Peau Neuve", types=("album",),
        preuve="https://www.deezer.com/album/927357171",
    ),
    Correction(
        item_id="e3aec491", titre="Deadline", types=("album",),
        preuve="https://www.deezer.com/album/926950431",
    ),
    # --- Les recos des fiches fusionnees, alignees sur le survivant --------
    # La fusion reporte les mentions mais ne touche pas aux recos : sans ces
    # lignes, la carte d'episode garderait l'ancien titre ou createur.
    Correction(
        item_id="0099e3e6", titre="The Joe Rogan Experience",
        titre_corrige="The Joe Rogan Experience",
        createur_faux=(None,), createur="Joe Rogan",
        preuve="https://en.wikipedia.org/wiki/The_Joe_Rogan_Experience",
    ),
    Correction(
        item_id="0c723800", titre="Bloqués", titre_corrige="Bloqués",
        preuve="https://fr.wikipedia.org/wiki/Bloqu%C3%A9s",
    ),
    Correction(
        item_id="26449f22", titre="Notes pour trop tard",
        titre_corrige="Notes pour trop tard",
        preuve="https://www.lacoccinelle.net/1260496-orelsan-notes-pour-trop-tard-ft-ibeyi.html",
    ),
    Correction(
        item_id="2407684e", titre="Paul Dechavanne",
        titre_corrige="Paul Dechavanne",
        createur_faux=(None, "Paul de Chavanne"), createur="Paul Dechavanne",
        types=("artiste",),
        preuve="https://www.billetreduc.com/spectacle-paul-dechavanne.htm",
    ),
    Correction(
        item_id="b0fd5e1f", titre="Outer Wilds",
        createur_faux=(None,), createur="Mobius Digital",
        preuve="https://en.wikipedia.org/wiki/Outer_Wilds",
    ),
    Correction(
        item_id="7693d750", titre="Vérino", titre_corrige="Vérino",
        createur_faux=(None, "Olivier Balestrier"), createur="Vérino",
        types=("artiste", "chaine"),
        preuve="https://www.billetreduc.com/artiste/verino",
    ),
    Correction(
        item_id="a1994a10", titre="The Witness",
        createur_faux="Thekla, Inc.", createur="Jonathan Blow",
        preuve="https://en.wikipedia.org/wiki/The_Witness_(2016_video_game)",
    ),
    Correction(
        item_id="936c2d69", titre="300 000 ans", titre_corrige="300 000 ans",
        createur_faux="Manon", createur="Manon Bril",
        preuve="https://www.infoconcert.com/spectacle/300-000-ans-14879/dates",
    ),
    Correction(
        # Un lieu n'a pas de createur (regle de `corrections_reco_anomalies`,
        # ubm-2719 et ubm-2830) : ni le nom du club, ni sa fondatrice, que
        # portait la fiche fusionnee.
        item_id="372c8ea6", titre="Barbès Comedy Club",
        titre_corrige="Barbès Comedy Club",
        createur_faux=("Barbès Comedy Club", "Shirley Souagnon"),
        retirer_createur=True,
        preuve="https://www.paris.fr/pages/decouvrez-la-scene-barbes-le-comedy-club-en-vogue-a-paris-23238",
    ),
)

#: Mentions validees a ecarter, et pourquoi.
MENTIONS_A_ECARTER: dict[str, str] = {
    # Meme instant (00:51:20 contre 00:51:22) et meme phrase que la reco
    # ubm-1368 « Balade Mentale ». « Christophe Pauly » est l'attribution
    # fautive deja retiree de Balade Mentale ; cette mention sans reco
    # comptait la meme recommandation une seconde fois.
    "ubm-1560": "doublon de ubm-1368 (Balade Mentale)",
}


def ecarter_mentions(ecarts: dict[str, str], *, apply: bool) -> int:
    """Passe en `discarded` les mentions listees encore validees."""
    n = 0
    for chemin in sorted(common.MENTIONS_DIR.rglob("*.json")):
        doc = json.loads(chemin.read_text(encoding="utf-8"))
        if doc.get("id") not in ecarts or doc.get("status") != "validated":
            continue
        doc["status"] = "discarded"
        log.info("mention %s ecartee : %s", doc["id"], ecarts[doc["id"]])
        n += 1
        if apply:
            chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    return n


def executer(*, apply: bool) -> dict[str, Any]:
    fusions = fusionner(GROUPES, apply=apply)
    corrections = corriger(apply=apply, corrections=CORRECTIONS)
    ecartees = ecarter_mentions(MENTIONS_A_ECARTER, apply=apply)
    return {"fusions": fusions, "corrections": corrections, "ecartees": ecartees}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(apply=args.apply)
    f, c = rapport["fusions"], rapport["corrections"]
    log.info("%d fusion(s), %d fiche(s) supprimee(s), %d mention(s) reportee(s) ; "
             "%d fiche(s) et %d reco(s) corrigee(s) ; %d mention(s) ecartee(s)",
             f["fusions"], f["supprimes"], f["mentions_reportees"],
             c["items"], c["recos"], rapport["ecartees"])
    for refus in f["refus"]:
        log.warning("REFUS %s", refus)
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 1 if f["refus"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
