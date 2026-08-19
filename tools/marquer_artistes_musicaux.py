"""
marquer_artistes_musicaux.py — distinguer un musicien d'un artiste tout court.

LE PROBLEME
-----------
La page `/musique` retient les types `musique`, `album` et `artiste`. Or
`artiste` est generique : Albert Dupontel et Hakim Jemili le portent, et se
retrouvaient dans la galerie musicale aux cotes d'Orelsan. Signale a la
relecture du 2026-08-19.

Sur les 358 artistes du corpus, 303 ne portent QUE ce type. Rien, dans l'item,
ne dit s'ils font de la musique.

LE SIGNAL EST DANS LES RECOS
----------------------------
Une reco de type `artiste` qui porte un lien Deezer, Spotify, Bandcamp, Qobuz,
Apple Music ou YouTube Music designe un musicien : personne ne pose un lien
d'ecoute sur un acteur. 79 titres sur 173 sont dans ce cas.

Ces liens ont ete poses et verifies un par un lors des vagues de juillet et
d'aout — c'est une donnee curee, pas une heuristique.

ON NE CREE AUCUN TYPE
---------------------
28 items portent deja `['artiste', 'musique']` : la convention existe. On la
propage, ce qui evite d'ajouter un quatorzieme type — une operation qui touche
six endroits sur ce projet.

CE QUE CA NE REGLE PAS
----------------------
Un musicien dont aucune reco ne porte de lien d'ecoute reste non marque. Le
manque est du cote des liens, pas du type : il se comblera quand ces recos
seront enrichies.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from collections.abc import Sequence
from typing import Any

import common  # type: ignore[attr-defined]

log = logging.getLogger("artistes_musicaux")

#: Les plateformes d'ECOUTE. Un lien vers l'une d'elles atteste d'un musicien.
#: `youtube.com` n'y figure pas : tout le monde a une chaine YouTube.
PLATEFORMES = re.compile(
    r"deezer\.com|open\.spotify\.com|music\.apple\.com|qobuz\.com"
    r"|bandcamp\.com|music\.youtube\.com",
    re.IGNORECASE,
)

TYPE_ARTISTE = "artiste"
TYPE_MUSIQUE = "musique"


def _titres_musicaux() -> set[str]:
    """Les titres d'artistes dont une reco PUBLIEE porte un lien d'ecoute."""
    trouves: set[str] = set()
    for chemin in common.RECOS_DIR.rglob("*.json"):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # Une reco ecartee a ete jugee hors sujet : s'y fier reviendrait a
        # marquer sur une donnee que l'editeur a retiree.
        if doc.get("status") == "discarded":
            continue
        if TYPE_ARTISTE not in (doc.get("types") or []):
            continue
        urls = [lien.get("url") or "" for lien in (doc.get("links") or [])
                if isinstance(lien, dict)]
        externes = json.dumps(doc.get("externalIds") or {}, ensure_ascii=False)
        if any(PLATEFORMES.search(u) for u in urls) or PLATEFORMES.search(externes):
            trouves.add((doc.get("title") or "").strip().lower())
    trouves.discard("")
    return trouves


def executer(*, apply: bool) -> dict[str, Any]:
    """Marque les items artistes reconnus musicaux. Renvoie un rapport."""
    musicaux = _titres_musicaux()
    marques = 0
    for chemin in sorted(common.ITEMS_DIR.rglob("*.json")):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        types = doc.get("types") or []
        if TYPE_ARTISTE not in types or TYPE_MUSIQUE in types:
            continue
        if (doc.get("title") or "").strip().lower() not in musicaux:
            continue
        marques += 1
        log.info("%s « %s »", doc.get("id"), doc.get("title"))
        if not apply:
            continue
        # Ajoute A LA FIN : `types[0]` sert de type primaire a l'affichage, et
        # un artiste doit rester un artiste sur sa carte.
        doc["types"] = [*types, TYPE_MUSIQUE]
        chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return {"titres_musicaux": len(musicaux), "marques": marques}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ajoute le type `musique` aux artistes dont une reco "
                    "publiee porte un lien vers une plateforme d'ecoute.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(apply=args.apply)
    log.info("%d titre(s) musical(aux) reconnu(s), %d item(s) marque(s)",
             rapport["titres_musicaux"], rapport["marques"])
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
