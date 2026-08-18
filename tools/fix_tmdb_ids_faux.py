"""
fix_tmdb_ids_faux.py — quatre oeuvres portaient l'identifiant d'une autre.

CE QUE CA CASSAIT
-----------------
L'identifiant TMDB n'est pas une metadonnee dormante : il alimente le lien
« fiche », la page « où regarder » et la liste des diffuseurs affichee sur la
page de l'oeuvre. Une erreur s'y voit donc directement.

La page « Drive » (Nicolas Winding Refn, 2011) portait `movie/1018`, qui EST
« Mulholland Drive » (David Lynch, 2001). Elle annoncait 19 diffuseurs — ceux
de Mulholland Drive — et son `watchPage` disait litteralement
`1018-mulholland-drive`. Un visiteur cliquant « où regarder » atterrissait sur
un autre film.

COMMENT ON LES A TROUVEES
-------------------------
Par la garde de `fusion_items_doublons`, le 2026-08-18. Elle refuse de
fusionner deux items aux titres divergents meme quand leur identifiant TMDB
coincide — et c'est ce refus, sur « Drive » contre « Mulholland Drive », qui a
revele que l'identifiant lui-meme mentait.

POURQUOI DEUX SONT CORRIGES ET DEUX RETIRES
-------------------------------------------
Corriger suppose de connaitre le bon identifiant :

  « Drive » -> movie/64690, verifie contre l'API (Drive, 2011).
  « Iris »  -> tv/271593, verifie contre l'API (Iris, 2024, creee par Doria
              Tillier, diffusee par Canal+). Corroboration independante : les
              recos ubm-0187 et ubm-0210 portaient DEJA le lien visible vers
              tv/271593, alors que leur identifiant machine restait faux. Le
              lien affiche avait ete corrige, la donnee non.

Pour « Mortal » et « Bagarre », aucun remplacant n'est etabli :

  « Mortal »  portait tv/90591 = « Pecado Mortal », telenovela bresilienne.
              Ses deux mentions ne permettent pas de trancher — l'une dit
              seulement « Mortal, je ne connaissais pas », l'autre parle de
              deneigement et n'est meme pas une oeuvre.
  « Bagarre » portait movie/49064 = « Picture Snatcher » (1933), quand la
              citation dit « aller voir Bagar le 15 avril » : un spectacle de
              Julien Royal, qui n'a pas de fiche film.

Inventer un identifiant plausible serait pire que son absence : il ne se
verifie plus une fois ecrit. On retire donc, sans remplacer.

CE QUI N'EST PAS RECOPIE
------------------------
`watchProviders` est SUPPRIME. La disponibilite d'une oeuvre change tous les
mois ; figer un instantane dans une table de code le condamne a pourrir. Le
`watchPage`, lui, se DEDUIT de l'identifiant : il est reconstruit.

CE QUI N'EST PAS DANS LA TABLE, ET POURQUOI
-------------------------------------------
« Mulholland Drive » (item c9f6b3f4, reco ubm-0968) porte movie/1018 a bon
droit — c'est lui, l'oeuvre. Le corriger inverserait l'erreur.

« Bref 2 » n'y est pas non plus. Il partage tv/60715 avec « Bref », ce qui
ressemblait a une collision — mais l'API montre que TMDB liste « bref. 2 »
(2025) comme la SAISON 2 de cette meme fiche. L'identifiant est donc correct ;
l'annoncer comme faux etait une erreur d'analyse, corrigee ici.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

import common  # type: ignore[attr-defined]
from dataset_fixes import Change, add_common_args, run

#: `id du document` -> (titre ATTENDU, identifiant ACTUEL attendu,
#:                      nouvel identifiant ou None, type TMDB ou None).
#:
#: Les deux premiers champs sont des GARDES : si le titre a change ou si
#: quelqu'un est deja passe, l'entree ne s'applique pas. Fonctionne pour les
#: recos (`ubm-XXXX`) comme pour les items (identifiant hexadecimal).
CORRECTIONS: dict[str, tuple[str, int, int | None, str | None]] = {
    # --- Corriges : le bon identifiant est etabli -------------------------
    "44695732": ("Drive", 1018, 64690, "movie"),      # item
    "ubm-0462": ("Drive", 1018, 64690, "movie"),      # reco (ecartee)
    "63c35f4b": ("Iris", 31505, 271593, "tv"),        # item
    "ubm-0187": ("Iris", 31505, 271593, "tv"),        # reco
    "ubm-0210": ("Iris", 31505, 271593, "tv"),        # reco
    # --- Retires : aucun remplacant etabli --------------------------------
    "4856e2ad": ("Mortal", 90591, None, None),        # item
    "ubm-0055": ("Mortal", 90591, None, None),        # reco (ecartee)
    "ubm-0322": ("Mortal", 90591, None, None),        # reco (ecartee)
    "44d74324": ("Bagarre", 49064, None, None),       # item
}

#: Le motif de chaque decision. Sans lui, personne ne pourra la rejuger.
POURQUOI: dict[str, str] = {
    "44695732": ("movie/1018 EST « Mulholland Drive » (Lynch, 2001). Le vrai "
                 "« Drive » de Nicolas Winding Refn (2011) est movie/64690, "
                 "verifie contre l'API. L'item annoncait 19 diffuseurs herites "
                 "du mauvais film."),
    "ubm-0462": ("Meme erreur que l'item 44695732, sur la reco correspondante."),
    "63c35f4b": ("tv/31505 est une serie coreenne de 2009. L'« Iris » du "
                 "corpus est celle de Doria Tillier (Canal+, 2024) = "
                 "tv/271593, verifie contre l'API."),
    "ubm-0187": ("Meme erreur. Cette reco porte DEJA le lien visible vers "
                 "tv/271593 : seul l'identifiant machine etait reste faux."),
    "ubm-0210": ("Meme cas que ubm-0187, meme oeuvre, meme lien visible deja "
                 "correct."),
    "4856e2ad": ("tv/90591 est « Pecado Mortal », telenovela bresilienne. "
                 "Aucun remplacant n'est etabli : les deux mentions ne "
                 "permettent pas de dire de quelle oeuvre il s'agit."),
    "ubm-0055": ("Meme identifiant faux que l'item 4856e2ad."),
    "ubm-0322": ("Meme identifiant faux que l'item 4856e2ad."),
    "44d74324": ("movie/49064 est « Picture Snatcher » (1933). La citation dit "
                 "« aller voir Bagar le 15 avril » : un spectacle de Julien "
                 "Royal, qui n'a pas de fiche film."),
}


def _watch_page(tmdb_type: str, tmdb_id: int) -> str:
    """L'adresse « où regarder », deduite de l'identifiant.

    Le corpus ecrit parfois un slug (`/movie/1018-mulholland-drive/watch`),
    mais TMDB l'ignore : le laisser tomber evite d'avoir a le fabriquer, et
    supprime une occasion de se tromper — c'est precisement ce slug qui
    affichait « mulholland-drive » sur la page « Drive ».
    """
    return f"https://www.themoviedb.org/{tmdb_type}/{tmdb_id}/watch?locale=FR"


def transform(doc: dict[str, Any]) -> list[Change]:
    """Corrige ou retire l'identifiant TMDB fautif. Mute `doc` en place."""
    entree = CORRECTIONS.get(doc.get("id") or "")
    if entree is None:
        return []
    titre_attendu, ancien, nouveau, tmdb_type = entree
    if doc.get("title") != titre_attendu:
        return []
    ext = doc.get("externalIds")
    if not isinstance(ext, dict) or ext.get("tmdb") not in (ancien, str(ancien)):
        return []

    avant_tmdb = ext.get("tmdb")
    changes = [Change(field="externalIds.tmdb", before=avant_tmdb,
                      after=nouveau)]
    if nouveau is None:
        ext.pop("tmdb", None)
        ext.pop("tmdbType", None)
        if "watchPage" in ext:
            changes.append(Change(field="externalIds.watchPage",
                                  before=ext["watchPage"], after=None))
            del ext["watchPage"]
    else:
        # ASYMETRIE DES DEUX SCHEMAS : `content.config.ts` declare
        # `tmdb: z.string()` cote RECO et `z.number().int()` cote ITEM. Ecrire
        # un entier dans une reco ARRETE le build — c'est arrive le 2026-08-18
        # sur ubm-0187. On preserve donc le type d'origine plutot que d'en
        # imposer un, ce qui rend l'outil juste pour les deux collections sans
        # avoir a savoir laquelle il traite.
        ext["tmdb"] = str(nouveau) if isinstance(ext.get("tmdb"), str) else nouveau
        ext["tmdbType"] = tmdb_type
        avant_page = ext.get("watchPage")
        if avant_page is not None:
            ext["watchPage"] = _watch_page(tmdb_type or "", nouveau)
            changes.append(Change(field="externalIds.watchPage",
                                  before=avant_page, after=ext["watchPage"]))
    # Un `externalIds` vide n'apporte rien et encombre le fichier.
    if not ext:
        doc.pop("externalIds", None)
    # La liste des diffuseurs decrivait l'autre oeuvre. On la SUPPRIME plutot
    # que d'en figer une nouvelle : la disponibilite change tous les mois.
    if "watchProviders" in doc:
        changes.append(Change(field="watchProviders",
                              before=len(doc["watchProviders"]), after=None))
        del doc["watchProviders"]
    return changes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Corrige les identifiants TMDB qui designaient une autre "
                    "oeuvre, et retire ceux dont le remplacant est inconnu.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Recos ET items : l'identifiant fautif vit dans les deux collections, et
    # n'en corriger qu'une desynchroniserait le corpus.
    run(transform, args, roots=(common.RECOS_DIR, common.ITEMS_DIR),
        extra_report={"corrections": len(CORRECTIONS)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
