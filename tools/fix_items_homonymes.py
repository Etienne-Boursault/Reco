"""
fix_items_homonymes.py — onze items portaient l'identifiant d'un homonyme.

CE QUI ETAIT CASSE
------------------
Les items sont apparies a TMDB par leur titre. Onze d'entre eux ont attrape un
HOMONYME — parfois vieux d'un demi-siecle, parfois d'un autre pays. La reco
correspondante, elle, portait le bon identifiant : les recos ont ete corrigees
a la main au fil du temps, les items sont restes sur leur appariement
automatique.

L'incoherence se lisait DANS L'ITEM LUI-MEME. « Fantomas » pointait le film
muet de 1913 tout en creditant Jean Marais, qui joue dans celui de 1964.
« Vice » pointait « Vice-versa » de Pixar en creditant Adam McKay. « Run »
pointait « Sauve qui peut » (1965) en creditant Phoebe Waller-Bridge.

L'identifiant n'est pas dormant : il alimente le lien « fiche », la page
« où regarder » et la liste des diffuseurs affichee sur `/oeuvre/`.

COMMENT CHAQUE CAS A ETE PROUVE
-------------------------------
Deux temoins concordants, jamais un seul :

  1. l'API TMDB, interrogee AVEC LE TYPE. C'est essentiel : `movie/57774` est
     une comedie russe de 1998, `tv/57774` est la serie « Looking » (2014).
     Une verification qui ignore le type conclut de travers — la premiere
     passe s'y est laissee prendre.
  2. le `creator` de l'item, qui designe l'oeuvre que son propre identifiant
     contredit.

POURQUOI UNE TABLE, ET NON UNE REGLE
------------------------------------
La regle « quand item et reco divergent, l'item herite de la reco » aurait
traite ces onze cas d'un coup. Mais rien ne garantit qu'une reco ait toujours
raison contre son item : la supposition tient ici parce qu'elle a ete VERIFIEE
onze fois, pas parce qu'elle serait vraie par nature. Une table dit ce qui a
ete verifie ; une regle affirmerait davantage qu'on ne sait.

La GARDE PERMANENTE, elle, est une regle : `tests/test_corpus_liens_tmdb.py`
interdit desormais qu'un item et une reco de meme titre designent des fiches
differentes. Elle attrapera les prochains sans rien presumer de qui a raison.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

import common  # type: ignore[attr-defined]
from dataset_fixes import Change, add_common_args, run

#: `id de l'item` -> (titre ATTENDU, identifiant ACTUEL, type ACTUEL,
#:                    nouvel identifiant, nouveau type).
#:
#: Les trois premiers champs sont des GARDES : si le corpus a bouge depuis la
#: verification, l'entree ne s'applique plus.
CORRECTIONS: dict[str, tuple[str, int, str, int, str]] = {
    "685f7d48": ("Brazil", 386948, "movie", 68, "movie"),
    "570ac224": ("Fantomas", 319287, "movie", 1871, "movie"),
    "83328ade": ("La jeune fille et la mort", 818681, "movie", 10531, "movie"),
    "57ed6444": ("Looking", 236338, "tv", 57774, "tv"),
    "9ada6868": ("Panique", 96903, "movie", 43462, "movie"),
    "0cbdddeb": ("Papa", 523926, "movie", 59163, "movie"),
    "3b41f743": ("Run", 11912, "tv", 87393, "tv"),
    "8c792e21": ("The Legend of Hei", 16339, "tv", 620249, "movie"),
    "3b1d98aa": ("Titanic", 102041, "movie", 597, "movie"),
    "332b5f30": ("To Be or Not to Be", 22998, "movie", 198, "movie"),
    "05d956f0": ("Vice", 150540, "movie", 429197, "movie"),
}

#: Les deux temoins de chaque decision.
POURQUOI: dict[str, str] = {
    "685f7d48": ("movie/386948 est « Beautiful Brazil » (1952). L'item credite "
                 "Terry Gilliam, dont le « Brazil » est movie/68 (1985) — et "
                 "c'est celui que la reco ubm-0966 designe."),
    "570ac224": ("movie/319287 est le « Fantomas » MUET de 1913. L'item credite "
                 "Jean Marais, qui joue dans celui de 1964 (movie/1871) ; la "
                 "citation dit « avec deux Funès et Jean Marais »."),
    "83328ade": ("movie/818681 est un film de 1990. L'item credite Roman "
                 "Polanski, dont « La Jeune Fille et la Mort » est de 1994 "
                 "(movie/10531)."),
    "57ed6444": ("tv/236338 est « Looking up to Magical Girls » (2024). L'item "
                 "credite HBO, et la serie « Looking » de 2014 est tv/57774. "
                 "Attention : movie/57774 est une comedie russe sans rapport — "
                 "le TYPE fait partie de l'identifiant."),
    "9ada6868": ("movie/96903 est « Panique! » (2009). L'item credite Julien "
                 "Duvivier, dont « Panique » est de 1947 (movie/43462) ; la "
                 "citation dit « Panique de Duvi[vi]er »."),
    "0cbdddeb": ("movie/523926 est un « Papa » de 2018. L'item credite Maurice "
                 "Barthelemy, dont le film est de 2005 (movie/59163)."),
    "3b41f743": ("tv/11912 est « Sauve qui peut » (1965). L'item credite "
                 "Waller-Bridge, dont « RUN » est tv/87393 (2020)."),
    "8c792e21": ("tv/16339 est « The Legend of Brown Sugar Chivalries » (2008). "
                 "« The Legend of Hei » est un FILM d'animation de 2019, "
                 "movie/620249 — le type change donc aussi."),
    "3b1d98aa": ("movie/102041 est le documentaire « James Cameron : la verite "
                 "sur le Titanic » (2012). L'item s'intitule « Titanic » tout "
                 "court : c'est le film de 1997, movie/597. Un autre item "
                 "(4f52ea73) le porte deja — la fusion les reunira."),
    "332b5f30": ("movie/22998 est le remake de Mel Brooks (1983). L'item credite "
                 "Ernst Lubitsch, dont le film est de 1942 (movie/198) ; la "
                 "citation dit « To Be [or] Not To Be de Lubitsch »."),
    "05d956f0": ("movie/150540 est « Vice-versa » de Pixar. L'item credite Adam "
                 "McKay, dont « Vice » est movie/429197 (2018)."),
}


def transform(doc: dict[str, Any]) -> list[Change]:
    """Remplace l'identifiant de l'homonyme. Mute `doc` en place."""
    entree = CORRECTIONS.get(doc.get("id") or "")
    if entree is None:
        return []
    titre, ancien, ancien_type, nouveau, nouveau_type = entree
    if doc.get("title") != titre:
        return []
    ext = doc.get("externalIds")
    if not isinstance(ext, dict):
        return []
    if ext.get("tmdb") not in (ancien, str(ancien)) or ext.get("tmdbType") != ancien_type:
        return []

    changes = [Change(field="externalIds.tmdb", before=ext.get("tmdb"),
                      after=nouveau)]
    # Le type d'origine est preserve : les items ecrivent un entier, mais rien
    # n'interdit qu'un autre appelant passe une chaine (cf. l'asymetrie des
    # deux schemas, corrigee dans fix_tmdb_ids_faux).
    ext["tmdb"] = str(nouveau) if isinstance(ext.get("tmdb"), str) else nouveau
    ext["tmdbType"] = nouveau_type
    # `watchPage` DERIVAIT de l'ancien identifiant : le garder pointerait
    # encore l'homonyme. On le retire, le pipeline le reconstruira.
    if "watchPage" in ext:
        changes.append(Change(field="externalIds.watchPage",
                              before=ext["watchPage"], after=None))
        del ext["watchPage"]
    # Les diffuseurs decrivaient la disponibilite de l'autre oeuvre. On ne les
    # recopie pas : cette information change tous les mois.
    if "watchProviders" in doc:
        changes.append(Change(field="watchProviders",
                              before=len(doc["watchProviders"]), after=None))
        del doc["watchProviders"]
    return changes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remplace, dans les items, l'identifiant TMDB d'un "
                    "homonyme par celui de l'oeuvre reellement designee.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Items SEULEMENT : ce sont eux qui portent l'erreur, les recos ont raison.
    run(transform, args, roots=(common.ITEMS_DIR,),
        extra_report={"corrections": len(CORRECTIONS)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
