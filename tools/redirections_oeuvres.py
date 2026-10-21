"""
redirections_oeuvres.py — une fiche fusionnee laisse une adresse qui redirige.

POURQUOI
--------
La page d'une oeuvre vit a `/<source>/oeuvre/<id>`. Fusionner deux fiches
supprime le perdant : son adresse, deja indexee et parfois partagee,
repondait 404. Le 2026-10-21, 264 adresses etaient dans ce cas, certaines
depuis aout.

La table `src/content/redirections-oeuvres.json` associe chaque ancienne
adresse a celle du survivant ; le serveur de production
(`src/server/redirections.mjs`) y repond par un 301, qui transmet aussi le
referencement.

QUI L'ALIMENTE
--------------
Les outils de fusion, au moment ou ils suppriment un perdant. Le fichier se
trouve a cote du dossier `items` : un test qui fusionne dans un dossier
temporaire ecrit donc sa table dans ce dossier, jamais dans le vrai corpus.
"""
from __future__ import annotations

import json
from pathlib import Path

NOM_FICHIER = "redirections-oeuvres.json"


def fichier_pour(dossier_items: Path) -> Path:
    return dossier_items.parent / NOM_FICHIER


def _dossier_items(chemin_item: Path) -> Path | None:
    for parent in chemin_item.parents:
        if parent.name == "items":
            return parent
    return None


def lire(fichier: Path) -> dict[str, str]:
    try:
        return json.loads(fichier.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def ecrire(fichier: Path, table: dict[str, str]) -> None:
    fichier.write_text(
        json.dumps(dict(sorted(table.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def ajouter(table: dict[str, str], ancienne: str, nouvelle: str) -> None:
    """Ajoute une redirection et raccourcit les chaines.

    Si A redirigeait deja vers l'adresse qui disparait, A pointe desormais
    directement sur la nouvelle : un visiteur ne traverse jamais deux 301.
    """
    for cle, cible in table.items():
        if cible == ancienne:
            table[cle] = nouvelle
    table[ancienne] = nouvelle
    table.pop(nouvelle, None)


def noter_fusion(chemin_perdant: Path, survivant_id: str) -> bool:
    """Note que la fiche `chemin_perdant` est remplacee par `survivant_id`.

    Rend `False` sans rien ecrire quand la source ne se deduit pas du chemin
    (`items/<source>/<id>.json` attendu) : sans source, pas d'adresse.
    """
    dossier = _dossier_items(chemin_perdant)
    if dossier is None:
        return False
    parties = chemin_perdant.relative_to(dossier).parts
    if len(parties) < 2:
        return False
    source = parties[0]
    fichier = fichier_pour(dossier)
    table = lire(fichier)
    ajouter(table, f"/{source}/oeuvre/{chemin_perdant.stem}",
            f"/{source}/oeuvre/{survivant_id}")
    ecrire(fichier, table)
    return True
