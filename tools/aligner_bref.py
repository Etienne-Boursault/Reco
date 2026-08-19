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

DEUXIEME PASSE (relecture du 2026-08-19)
----------------------------------------
YOUTUBE PASSE EN TETE. « il y a Disney+ mais il y a surtout YouTube en
priorite https://www.youtube.com/@Bref ». C'est la chaine officielle de la
serie (verifiee : `bref.`, UCWxt-Sphj4wcAoaIfhsALRg), et c'est la que les
episodes de la saison 1 se regardent librement — Disney+ demande un
abonnement. Le lien le plus utile passe donc devant.

La carte plafonne a six liens : ajouter YouTube a « Bref » en faisait sept.
« Ou regarder » sort — il pointait la page « watch » de TMDB, qui ne fait que
rediriger vers Disney+, deja present juste au-dessus.

L'ETOILE « LEUR OEUVRE ». « pense bien a mettre l'etoile "Leur oeuvre" puisque
ce sont eux qui parlent de leur propre oeuvre ». Verifie : Kyan Khojandi et
Navo sont les HOSTS d'« Un Bon Moment » (`sources/un-bon-moment.json`), et
Bref est leur serie. La politique du 2026-07-07 couvre exactement ce cas —
`guestWork` vaut pour l'auto-promo des invite·es ET des hosts, d'ou le libelle
« Leur oeuvre ».

A noter : dans aucun des seize episodes concernes Kyan ou Navo ne figure comme
INVITE. Ils parlent de Bref depuis leur fauteuil d'animateur, ce qui reste de
l'auto-promo au sens de la politique.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from dataset_fixes import Change, add_common_args, run

#: Le createur unique. Navo = Bruno Muschio ; Alain Chabat a produit, pas cree.
CREATEUR = "Kyan Khojandi, Navo"

#: Bref est la serie des HOSTS du podcast. Toute mention est donc de
#: l'auto-promo au sens de la politique du 2026-07-07, et porte l'etoile.
OEUVRE_DES_HOSTS = True

#: Les liens de reference, par titre normalise. L'ordre compte : la carte
#: n'en affiche que six, et coupe au-dela.
LIENS: dict[str, list[dict[str, str]]] = {
    "bref": [
        # La chaine officielle, en tete : les episodes de la saison 1 s'y
        # regardent sans abonnement.
        {"ethics": "neutral", "kind": "official", "label": "YouTube",
         "url": "https://www.youtube.com/@Bref"},
        {"ethics": "neutral", "kind": "streaming", "label": "Disney+",
         "url": "https://www.disneyplus.com/fr-fr/series/bref/2rCjFRmIlL2f"},
        {"ethics": "neutral", "kind": "info", "label": "AlloCiné",
         "url": "https://www.allocine.fr/series/ficheserie_gen_cserie=10520.html"},
        {"ethics": "neutral", "kind": "info", "label": "IMDb",
         "url": "https://www.imdb.com/title/tt2044128/"},
        {"ethics": "neutral", "kind": "info", "label": "TMDB",
         "url": "https://www.themoviedb.org/tv/60715"},
        # « Ou regarder » est sorti a la deuxieme passe : il pointait la page
        # « watch » de TMDB, qui ne fait que rediriger vers Disney+ ci-dessus.
        {"ethics": "neutral", "kind": "social", "label": "Instagram",
         "url": "https://www.instagram.com/kyankhojandi/"},
    ],
    "bref 2": [
        {"ethics": "neutral", "kind": "official", "label": "YouTube",
         "url": "https://www.youtube.com/@Bref"},
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

    # L'etoile « Leur oeuvre » : Kyan et Navo animent le podcast, Bref est
    # leur serie. Peu importe qui la cite dans l'episode — c'est bien leur
    # oeuvre qui passe a l'antenne.
    if reco.get("guestWork") is not OEUVRE_DES_HOSTS:
        changes.append(Change(field="guestWork", before=reco.get("guestWork"),
                              after=OEUVRE_DES_HOSTS))
        reco["guestWork"] = OEUVRE_DES_HOSTS

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
