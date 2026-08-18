"""
fix_ordre_liens.py — remonter le lien UTILE au-dessus de la coupe à six.

LE PROBLÈME
-----------
`RecoCard` n'affiche que six liens, et ce sont les DERNIERS de la liste qui
tombent. Or les liens ajoutés par une passe d'enrichissement arrivent, par
construction, à la fin : cinq recos d'« Une Bonne Soirée » avaient ainsi leur
lien Canal+ invisible, deux « John Wick » leur page « Où regarder », quatre
« Kaamelott » leur site officiel — relevé le 2026-08-18.

POURQUOI CORRIGER LA DONNÉE ET NON L'AFFICHAGE
----------------------------------------------
Trier à l'affichage réglait les onze cas, mais changeait AUSSI l'ordre des
liens auto-générés — et celui-là est intentionnel : le résolveur place
Bandcamp en tête parce qu'il est `indie`. Onze recos ne justifient pas une
régression silencieuse sur toutes les cartes musicales.

On réordonne donc la donnée, et UNIQUEMENT là où une coupe a lieu.

CE QUI EST PRÉSERVÉ
-------------------
Aucun lien n'est ajouté ni retiré : c'est une permutation. À priorité égale,
l'ordre curé est conservé — le tri est stable.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from dataset_fixes import Change, add_common_args, run

#: Nombre de liens affichés par `RecoCard` (cf. son `slice(0, 6)`).
AFFICHES = 6

#: Ce que le visiteur cherche, dans l'ordre : accéder à l'œuvre, se
#: renseigner, puis suivre l'auteur. Un `kind` inconnu se range au milieu.
PRIORITE = {"streaming": 0, "buy": 1, "borrow": 2, "info": 3,
            "official": 4, "social": 5}


def transform(reco: dict[str, Any]) -> list[Change]:
    """Réordonne `links` quand la reco en porte plus que la carte n'en montre."""
    liens = [lien for lien in (reco.get("links") or []) if isinstance(lien, dict)]
    if len(liens) <= AFFICHES or len(liens) != len(reco.get("links") or []):
        return []

    avant = [lien.get("url") for lien in liens]
    apres_liens = sorted(liens, key=lambda lien: PRIORITE.get(lien.get("kind"), 3))
    apres = [lien.get("url") for lien in apres_liens]
    if avant == apres:
        return []

    reco["links"] = apres_liens
    return [Change(field="links", before=avant, after=apres)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remonte les liens d'accès à l'œuvre au-dessus des six "
                    "affichés par la carte, dans les recos qui en portent plus.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(transform, args, extra_report={"affiches": AFFICHES})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
