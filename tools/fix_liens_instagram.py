"""
fix_liens_instagram.py — pose le lien Instagram, et seulement s'il reste
de la place.

POURQUOI CES HANDLES N'ÉTAIENT PAS AFFICHÉS
-------------------------------------------
299 recos publiées portent un `externalIds.instagram`. `merchants.ts` sait
pourtant en faire un lien — mais seulement dans `linksForArtist`, c'est-à-dire
dans le RÉSOLVEUR automatique, que `RecoCard` n'appelle QUE lorsque la reco n'a
aucun lien explicite. Or les passes de liens successives en ont donné à presque
tout le monde : le résolveur ne tourne plus, et le handle dort dans la donnée.

L'éditeur du site a tranché le 2026-08-18 : on l'affiche, mais en DERNIÈRE
priorité. Un compte Instagram dit où suivre la personne ; il ne dit pas où
écouter, lire ou regarder l'œuvre. Il ne doit donc jamais coûter sa place à un
lien qui, lui, y mène.

LE PLAFOND DE SIX EST APPLIQUÉ ICI, PAS SEULEMENT DEMANDÉ
---------------------------------------------------------
`RecoCard` fait un `slice(0, 6)`. Écrire un septième lien ne le rendrait pas
visible : cela évincerait le sixième. Ce module REFUSE donc d'écrire dès que la
carte affiche déjà six liens — même règle, même constante, que
`fix_liens_plateformes`, où l'ordre éditorial place Instagram après toutes les
plateformes d'écoute (Bandcamp, Deezer, Apple Music, Spotify, Qobuz, YT Music).

Le compte se fait sur ce que la carte AFFICHE, pas sur la longueur de `links` :
elle concatène `customLinks` puis `links`, déduplique par label en minuscules,
et coupe ensuite. Compter autrement ferait sauter un lien saisi à la main.

LE PIÈGE DE LA RECO SANS AUCUN LIEN
-----------------------------------
Une reco dont `links` est vide reçoit ses liens du résolveur automatique. Y
écrire un unique lien Instagram ne l'ajouterait pas : cela REMPLACERAIT tout ce
que le résolveur produisait — libraires, Deezer, JustWatch — par le seul
Instagram. Ces recos sont donc écartées ; leur handle, lui, continue d'être
servi par `linksForArtist`.

`kind: "social"` n'est pas décoratif : c'est la valeur de l'énumération du
schéma (`buy|borrow|streaming|info|official|social`) — une valeur hors liste
casse le build, c'est déjà arrivé avec `kind: "ticket"`. Elle vaut en outre
`5` dans la priorité de `fix_ordre_liens`, soit le dernier rang : le lien reste
en queue même si le corpus est retrié.
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from typing import Any

from dataset_fixes import Change, add_common_args, run

#: Nombre de liens affichés par `RecoCard` (cf. son `slice(0, 6)`).
AFFICHES = 6

#: Libellé du lien. Il sert AUSSI de clé de déduplication côté carte, qui
#: compare les labels en minuscules.
LABEL = "Instagram"

#: Valeurs du schéma (`content.config.ts`). Voir l'en-tête.
KIND = "social"
ETHICS = "neutral"

GABARIT_URL = "https://www.instagram.com/{}/"

#: Handle Instagram valide : 1 à 30 caractères parmi lettres/chiffres/`.`/`_`.
#: Copie DÉLIBÉRÉE de `IG_HANDLE_RE` (merchants.ts) : le handle est interpolé
#: dans un chemin d'URL, un handle libre y injecterait query ou segments.
HANDLE_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def handle_de(reco: dict[str, Any]) -> str | None:
    """Le handle nettoyé, ou `None` si absent ou inexploitable."""
    brut = (reco.get("externalIds") or {}).get("instagram")
    if not isinstance(brut, str):
        return None
    handle = brut.strip().lstrip("@")
    return handle if HANDLE_RE.match(handle) else None


def labels_affiches(reco: dict[str, Any]) -> list[str]:
    """Les libellés que la carte affichera, dans son ordre et sans doublon.

    Reproduit `RecoCard` : `customLinks` d'abord, puis `links`, déduplication
    par label en minuscules. Les entrées héritées mal formées sont ignorées
    plutôt que de faire tomber la passe sur les 3000 autres fichiers.
    """
    vus: list[str] = []
    sources = list(reco.get("customLinks") or []) + list(reco.get("links") or [])
    for lien in sources:
        if not isinstance(lien, dict):
            continue
        label = lien.get("label")
        if not isinstance(label, str):
            continue
        cle = label.strip().lower()
        if cle not in vus:
            vus.append(cle)
    return vus


def transform(reco: dict[str, Any]) -> list[Change]:
    """Ajoute le lien Instagram en fin de liste. Mute `reco` en place.

    Cinq refus, tous normaux : pas de handle exploitable, aucune liste de liens
    explicite (le résolveur ferait mieux, cf. en-tête), carte déjà pleine, lien
    Instagram déjà présent — par son label ou par son URL.
    """
    handle = handle_de(reco)
    if handle is None:
        return []

    liens = reco.get("links")
    if not isinstance(liens, list) or not liens:
        return []

    labels = labels_affiches(reco)
    if len(labels) >= AFFICHES or LABEL.lower() in labels:
        return []

    url = GABARIT_URL.format(handle)
    if any(isinstance(lien, dict) and lien.get("url") == url for lien in liens):
        return []

    avant = [lien.get("url") for lien in liens if isinstance(lien, dict)]
    reco["links"] = liens + [
        {"label": LABEL, "url": url, "kind": KIND, "ethics": ETHICS}
    ]
    return [Change(field="links", before=avant, after=avant + [url])]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Affiche le compte Instagram des recos qui en portent un, "
                    "en dernière priorité : seulement si la carte a moins de "
                    "six liens, donc sans jamais en évincer un autre.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(transform, args, extra_report={"plafond_affichage": AFFICHES})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
