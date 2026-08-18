"""
fix_watchpage_coherent.py — l'adresse « où regarder » doit suivre son identifiant.

L'INVARIANT
-----------
`externalIds.watchPage` est l'adresse de la page « où regarder » sur TMDB. Elle
se DEDUIT de `externalIds.tmdb` et de `tmdbType` : meme identifiant, meme page.
Ce n'est pas une donnee independante, c'est un derive — et un derive ne peut
pas diverger de ce dont il derive.

CE QUE LA VIOLATION PRODUISAIT
------------------------------
Cinq recos violaient l'invariant le 2026-08-18, et chacune envoyait le visiteur
sur une AUTRE oeuvre que celle annoncee :

    « Vice » (Adam McKay, 2018)   -> « Vice-versa » (Pixar, 2015)      x2
    « Fantomas » (de Funes, 1964) -> « Fantomas », le muet de 1913
    « Looking » (2014)            -> « Looking up to Magical Girls » (2024)
    « Bagarre »                   -> « Picture Snatcher » (1933)

Dans les cinq cas, l'identifiant machine etait JUSTE : c'est l'adresse qui
mentait. Le bouton disait « Où regarder » et menait ailleurs.

POURQUOI UNE REGLE PLUTOT QU'UNE TABLE
--------------------------------------
Une table curee de cinq entrees n'aurait corrige que ces cinq-la. La regle vaut
pour tout le corpus et pour ce qui s'y ajoutera. La difference n'est pas
theorique : la reco « Bagarre » avait echappe au correctif cure de la veille,
qui ne visait que l'item du meme nom. Une regle n'oublie pas de cas.

CE QU'ELLE NE TOUCHE PAS
------------------------
Une adresse deja coherente est laissee TELLE QUELLE, slug compris. Le corpus
ecrit tantot `/tv/94801/watch`, tantot `/tv/94801-mortel/watch` ; TMDB ignore
le slug, les deux fonctionnent. Les normaliser produirait un diff de plusieurs
centaines de fichiers sans corriger quoi que ce soit.

Une adresse qui ne pointe pas TMDB est laissee aussi : on ne prend pas la main
sur ce qu'on ne sait pas lire.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from typing import Any

import common  # type: ignore[attr-defined]
from dataset_fixes import Change, add_common_args, run

#: `/movie/123` ou `/tv/456` dans une adresse TMDB. Le slug qui suit est
#: decoratif — TMDB ne le lit pas.
_ADRESSE = re.compile(r"themoviedb\.org/(movie|tv)/(\d+)")


def adresse_attendue(tmdb_type: str, tmdb_id: str | int) -> str:
    """L'adresse « où regarder » telle qu'elle decoule de l'identifiant."""
    return f"https://www.themoviedb.org/{tmdb_type}/{tmdb_id}/watch?locale=FR"


def transform(doc: dict[str, Any]) -> list[Change]:
    """Refait l'adresse si elle a derive, la supprime si elle est orpheline."""
    ext = doc.get("externalIds")
    if not isinstance(ext, dict):
        return []
    page = ext.get("watchPage")
    if not isinstance(page, str) or not page:
        return []
    trouve = _ADRESSE.search(page)
    if trouve is None:
        # Adresse hors TMDB : hors de notre juridiction.
        return []

    tmdb_id = ext.get("tmdb")
    tmdb_type = ext.get("tmdbType")
    if tmdb_id is None or not tmdb_type:
        # Plus d'identifiant : l'adresse ne derive plus de rien.
        changes = [Change(field="externalIds.watchPage", before=page, after=None)]
        del ext["watchPage"]
        if not ext:
            doc.pop("externalIds", None)
        return changes

    if (trouve.group(1), trouve.group(2)) == (str(tmdb_type), str(tmdb_id)):
        return []  # deja coherente, slug ou pas

    ext["watchPage"] = adresse_attendue(str(tmdb_type), tmdb_id)
    return [Change(field="externalIds.watchPage", before=page,
                   after=ext["watchPage"])]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refait `externalIds.watchPage` quand elle a derive de "
                    "`externalIds.tmdb`, et la supprime quand l'identifiant a "
                    "disparu.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Recos ET items : le champ vit dans les deux collections.
    run(transform, args, roots=(common.RECOS_DIR, common.ITEMS_DIR))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
