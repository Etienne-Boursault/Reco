"""
purge_flags_attribution.py — retire le drapeau `attribution_suspect` la ou un
humain a deja tranche.

CE QUE CE DRAPEAU VOULAIT DIRE
------------------------------
La review automatique du 7 au 18 juillet 2026 l'a pose quand `recommendedBy`
etait vide et qu'elle n'arrivait pas a decider qui recommandait. Exemple type,
sur `ubm-0041` : « Attribution floue (qui y etait hier ? guest ou host) →
recommendedBy vide ».

CE QUI S'EST PASSE ENSUITE
--------------------------
L'editeur du site a fait une passe MANUELLE, un cas a la fois, et a renseigne
le nom. Sur `ubm-0041`, le champ etait absent avant le commit 76b1bbac
(« validations manuelles de la session ») et vaut « Hakim Jemili » apres. Sur
20 cas tires au hasard parmi les 344, les 20 noms viennent d'un commit humain.

Le drapeau, lui, n'a pas bouge. La fiche annonce donc une attribution douteuse
que quelqu'un a pourtant tranchee. Le 2026-08-18, cette lecture a fait classer
ces 344 fiches en tete d'un backlog d'ameliorations : le defaut n'etait pas
dans les donnees, il etait dans le drapeau. Sans cette passe, chaque audit
suivant refera la meme erreur.

POURQUOI ON NE SUPPRIME PAS
---------------------------
L'ambiguite d'origine etait REELLE : « qui y etait hier, l'invite ou l'hote ? »
reste une question legitime, et la reponse humaine peut se rediscuter. Le
drapeau est donc deplace dans `flagsResolved`, pas efface. Ce qui cesse, c'est
la fausse alerte — pas la memoire de ce qui l'a motivee.

PERIMETRE
---------
Ce seul drapeau. Les autres (`title_suspect` 545, `duplicate_suspect` 462,
`guest_missing` 351, `timestamp_suspect` 26, `link_suspect` 13) n'ont pas de
critere de resolution lisible dans la donnee : rien n'y dit si le titre douteux
a ete corrige ou simplement laisse tel quel. Les purger demanderait de relire
chaque cas, ce qui est un autre travail.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from dataset_fixes import Change, add_common_args, run

#: Le drapeau traite. Volontairement unique : cf. PERIMETRE ci-dessus.
DRAPEAU = "attribution_suspect"


def transform(reco: dict[str, Any]) -> list[Change]:
    """Deplace `attribution_suspect` vers `flagsResolved`. Mute `reco` en place.

    Trois conditions, toutes necessaires :
      - le drapeau est present ;
      - `reviewedByHuman` vaut exactement `True` — une chaine « true » ou un 1
        traineraient dans la donnee heritee sans prouver qu'un humain a lu ;
      - `recommendedBy` porte un nom : c'est LA resolution. Sans nom, rien n'a
        ete tranche et le drapeau dit encore quelque chose de vrai.
    """
    review = reco.get("agentReview")
    if not isinstance(review, dict):
        return []
    flags = review.get("flags")
    if not isinstance(flags, list) or DRAPEAU not in flags:
        return []
    if review.get("reviewedByHuman") is not True:
        return []
    if not (reco.get("recommendedBy") or "").strip():
        return []

    avant = list(flags)
    review["flags"] = [f for f in flags if f != DRAPEAU]
    resolus = review.get("flagsResolved")
    if not isinstance(resolus, list):
        resolus = []
    if DRAPEAU not in resolus:
        resolus.append(DRAPEAU)
    review["flagsResolved"] = resolus
    return [Change(field="agentReview.flags", before=avant, after=review["flags"])]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retire le drapeau `attribution_suspect` des fiches dont "
                    "un humain a deja renseigne l'attribution, en conservant "
                    "la trace dans `flagsResolved`.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(transform, args, extra_report={"drapeau": DRAPEAU})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
