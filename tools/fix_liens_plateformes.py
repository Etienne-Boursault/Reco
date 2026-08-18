"""
fix_liens_plateformes.py — pose les liens d'écoute vérifiés.

D'OÙ VIENNENT CES LIENS
-----------------------
Passe du 2026-08-18 : onze agents ont cherché, sur Deezer, Spotify, Apple
Music, Bandcamp, Qobuz et YouTube Music, les plateformes manquantes des recos
`musique`, `album`, `artiste` (musical) et `podcast`. Aucun n'avait le droit
d'écrire dans le corpus. Chaque lien a été revérifié ensuite, avec l'outil
propre à sa plateforme — une vérification uniforme donne des faux négatifs en
masse : YouTube répond son mur de consentement à une requête nue, et Deezer
sert les podcasts sous `/podcast/` et non `/show/`.

La table vit dans `tools/data/liens_plateformes.json` plutôt que dans ce
fichier : plusieurs centaines d'entrées en littéral Python seraient illisibles,
et le fichier passerait la limite de 500 lignes du dépôt. Chaque entrée y porte
sa PREUVE, comme le veut la doctrine des correctifs curés.

LE PLAFOND DE SIX EST APPLIQUÉ ICI, PAS SEULEMENT DEMANDÉ
---------------------------------------------------------
`RecoCard` n'affiche que six liens. Une consigne donnée à un agent est un vœu ;
ce module, lui, REFUSE d'écrire au-delà. Sans quoi une reco recevrait des liens
que personne ne verrait, tout en paraissant complète.

L'ordre d'écriture suit l'éthique du dépôt : Bandcamp d'abord, l'artiste y
étant mieux rémunéré, puis les plateformes de streaming.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dataset_fixes import Change, add_common_args, run

#: Nombre de liens affichés par `RecoCard` (cf. son `slice(0, 6)`).
AFFICHES = 6

#: Priorité d'écriture quand plusieurs plateformes sont candidates pour les
#: mêmes places. Bandcamp d'abord : c'est le choix éditorial du site.
PRIORITE = {"Bandcamp": 0, "Deezer": 1, "Apple Music": 2, "Spotify": 3,
            "Qobuz": 4, "YT Music": 5}

DONNEES = Path(__file__).with_name("data") / "liens_plateformes.json"


def charger(chemin: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Table `id de reco` → liens vérifiés, groupés et triés par priorité."""
    source = chemin or DONNEES
    if not source.exists():
        return {}
    par_reco: dict[str, list[dict[str, Any]]] = {}
    for entree in json.loads(source.read_text(encoding="utf-8")):
        par_reco.setdefault(entree["id"], []).append(entree)
    for liens in par_reco.values():
        liens.sort(key=lambda e: PRIORITE.get(e.get("label"), 9))
    return par_reco


TABLE = charger()


def transform(reco: dict[str, Any]) -> list[Change]:
    """Ajoute les liens vérifiés, sans jamais dépasser six au total."""
    prevus = TABLE.get(reco.get("id") or "")
    if not prevus:
        return []

    liens = list(reco.get("links") or [])
    presentes = {lien.get("url") for lien in liens if isinstance(lien, dict)}
    avant = [lien.get("url") for lien in liens if isinstance(lien, dict)]

    ajouts = []
    for e in prevus:
        if len(liens) + len(ajouts) >= AFFICHES:
            break  # la carte est pleine : au-delà, personne ne verrait le lien
        # La garde : si le titre a changé depuis la vérification, la reco peut
        # désigner autre chose.
        if reco.get("title") != e.get("titre_attendu"):
            continue
        if e["url"] in presentes:
            continue
        ajouts.append({"label": e["label"], "url": e["url"],
                       "kind": e.get("kind", "streaming"),
                       "ethics": e.get("ethics", "neutral")})
        presentes.add(e["url"])

    if not ajouts:
        return []
    reco["links"] = liens + ajouts
    return [Change(field="links", before=avant,
                   after=avant + [a["url"] for a in ajouts])]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pose les liens d'écoute vérifiés de la passe du "
                    "2026-08-18, sans jamais porter une reco au-delà des six "
                    "liens que la carte affiche.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(transform, args, extra_report={"liens_en_table": sum(len(v) for v in TABLE.values()),
                                       "recos_en_table": len(TABLE)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
