"""
aligner_bref.py — seize cartes pour la meme serie, seize versions differentes.

CE QUE LA RELECTURE A VU
------------------------
Une capture de `/recos` filtree sur « Bref » : seize cartes de la meme serie,
avec CINQ graphies de createur — « Kyan Khojandi », « Kyan Khojandi, Bruno
Muschio », « Kyan Khojandi, Navo », « Kyan Khojandi, Alain Chabat », et une
sans createur — et des jeux de liens allant de trois a six. Une carte pointait
meme YouTube la ou les quinze autres pointaient Disney+.

Chaque carte est une MENTION distincte, ce qui est normal. Mais l'oeuvre, elle,
est la meme : rien ne justifie qu'elle change de createur ou de liens d'une
carte a l'autre.

CE QUI EST RETENU, ET POURQUOI
------------------------------
Le createur : « Kyan Khojandi, Navo ». Navo est le nom de scene de Bruno
Muschio — les deux graphies designent la meme personne, et l'editeur a choisi
celle-ci. Alain Chabat sort : il a PRODUIT la serie, il ne l'a pas creee.

Les liens : ceux de la reco la plus complete, deja verifies un par un lors des
vagues de juillet. Six pour « Bref », soit exactement le plafond d'affichage
de la carte — un septieme serait invisible.

« Bref 2 » garde ses propres liens : c'est la saison 2, avec sa page Disney+
distincte. Elle partage en revanche le meme createur.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from dataset_fixes import Change, add_common_args, run

#: Le createur unique. Navo = Bruno Muschio ; Alain Chabat a produit, pas cree.
CREATEUR = "Kyan Khojandi, Navo"

#: Les liens de reference, par titre normalise. L'ordre compte : la carte
#: n'en affiche que six, et coupe au-dela.
LIENS: dict[str, list[dict[str, str]]] = {
    "bref": [
        {"ethics": "neutral", "kind": "streaming", "label": "Disney+",
         "url": "https://www.disneyplus.com/fr-fr/series/bref/2rCjFRmIlL2f"},
        {"ethics": "neutral", "kind": "info", "label": "AlloCiné",
         "url": "https://www.allocine.fr/series/ficheserie_gen_cserie=10520.html"},
        {"ethics": "neutral", "kind": "info", "label": "IMDb",
         "url": "https://www.imdb.com/title/tt2044128/"},
        {"ethics": "neutral", "kind": "info", "label": "TMDB",
         "url": "https://www.themoviedb.org/tv/60715"},
        {"ethics": "neutral", "kind": "streaming", "label": "Où regarder",
         "url": "https://www.themoviedb.org/tv/60715-bref/watch?locale=FR"},
        {"ethics": "neutral", "kind": "social", "label": "Instagram",
         "url": "https://www.instagram.com/kyankhojandi/"},
    ],
    "bref 2": [
        {"ethics": "neutral", "kind": "streaming", "label": "Disney+",
         "url": "https://www.disneyplus.com/browse/entity-b329134e-b113-49d6-827e-dd4e0616457f"},
        {"ethics": "neutral", "kind": "info", "label": "TMDB",
         "url": "https://www.themoviedb.org/tv/60715"},
        {"ethics": "neutral", "kind": "streaming", "label": "JustWatch",
         "url": "https://www.justwatch.com/fr/serie/bref"},
        {"ethics": "neutral", "kind": "social", "label": "Instagram",
         "url": "https://www.instagram.com/kyankhojandi/"},
    ],
}


def transform(reco: dict[str, Any]) -> list[Change]:
    """Aligne createur et liens sur la reference. Mute `reco` en place."""
    # Une reco ecartee ne s'affiche nulle part : l'aligner ne servirait a rien
    # et brouillerait la trace de ce qui a ete ecarte.
    if reco.get("status") == "discarded":
        return []
    titre = (reco.get("title") or "").strip().lower()
    reference = LIENS.get(titre)
    if reference is None:
        return []

    changes: list[Change] = []
    if reco.get("creator") != CREATEUR:
        changes.append(Change(field="creator", before=reco.get("creator"),
                              after=CREATEUR))
        reco["creator"] = CREATEUR

    avant = [lien.get("url") for lien in (reco.get("links") or [])
             if isinstance(lien, dict)]
    apres = [lien["url"] for lien in reference]
    if avant != apres:
        changes.append(Change(field="links", before=avant, after=apres))
        # REMPLACEMENT et non fusion : c'est le point de la demande, les
        # cartes doivent porter exactement les memes liens.
        reco["links"] = [dict(lien) for lien in reference]
    return changes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aligne le createur et les liens de toutes les recos "
                    "« Bref » et « Bref 2 » sur une reference unique.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(transform, args, extra_report={"createur": CREATEUR})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
