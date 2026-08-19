"""
nettoyer_type_autre.py — « autre » ne dit rien quand un vrai type existe.

CE QUE `AUTRE` VEUT DIRE
-----------------------
C'est le type de repli : l'oeuvre n'entre dans aucune des treize categories du
corpus. Il a un sens QUAND IL EST SEUL.

Accole a un vrai type, il ne dit plus rien. « Bref » portait
`types: ['autre', 'serie']` : c'est une serie, et « autre » n'ajoutait aucune
information.

CE QU'IL COUTAIT
----------------
Il en RETIRAIT, meme. `GalleryCard` prend `types[0]` comme type primaire, et
« autre » passe en tete par ordre alphabetique. La page `/series` affichait
donc le badge « AUTRE » sur « Bref », « Succession », « Iris », « Cher
Journal » et « Genre Humaine » — toutes des series. Signale a la relecture du
2026-08-19.

L'ordre alphabetique n'etait pas fortuit : la fusion des doublons du
2026-08-18 reunit les types avec `sorted(set(...))`, ce qui a pousse « autre »
en premiere position sur les items fusionnes.

CE QUE CET OUTIL NE FAIT PAS
----------------------------
Il ne touche pas aux 400 documents dont « autre » est le SEUL type. Leur
donner une categorie demande de savoir ce qu'est l'oeuvre — c'est un travail
de curation, pas de nettoyage, et aucune regle ne peut le deduire.

Le correctif d'AFFICHAGE vit a cote, dans `GalleryCard` : meme nettoyees, les
donnees peuvent redevenir bancales, et une carte ne doit jamais preferer
« autre » a un type qui dit quelque chose.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

import common  # type: ignore[attr-defined]
from dataset_fixes import Change, add_common_args, run

REPLI = "autre"


def transform(doc: dict[str, Any]) -> list[Change]:
    """Retire « autre » quand un autre type existe. Mute `doc` en place."""
    types = doc.get("types")
    if not isinstance(types, list):
        return []
    # L'ORDRE est preserve : la carte affiche `types[0]`, et reordonner
    # changerait le badge. On se contente d'oter `autre` et les doublons.
    garde: list[str] = []
    for t in types:
        if t != REPLI and t not in garde:
            garde.append(t)
    # « autre » SEUL est legitime : le retirer laisserait `types` vide, ce que
    # le schema refuse (`min(1)`), et arreterait le build.
    if not garde or garde == types:
        return []
    avant = list(types)
    doc["types"] = garde
    return [Change(field="types", before=avant, after=garde)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retire le type de repli « autre » des documents qui "
                    "portent deja un type plus precis.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(transform, args, roots=(common.RECOS_DIR, common.ITEMS_DIR))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
