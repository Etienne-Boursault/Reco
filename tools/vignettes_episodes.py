"""
vignettes_episodes.py — les vignettes d'episodes, servies par le site lui-meme.

POURQUOI
--------
Jusqu'au 2026-10-22, le site affichait les vignettes depuis `i.ytimg.com` et
Acast : chaque visiteur envoyait son adresse IP a Google sans avoir clique sur
rien, contre ce que promettent le manifeste et les mentions legales. Les
vignettes sont donc telechargees une fois, versionnees dans
`public/vignettes/`, et servies par le site.

LES NOMS
--------
`src/utils/vignettes.ts` recalcule les memes noms au build : les deux regles
doivent rester identiques.

- Video YouTube : `yt-<id>-mq.jpg` (320x180, catalogue) et `yt-<id>-hq.jpg`
  (480x360, page de l'episode).
- Sinon, l'image du flux : `ep-<sha1(url)[:12]><extension>`, une seule taille.

Un fichier deja present n'est jamais retelecharge. Usage :
`python vignettes_episodes.py --source un-bon-moment`.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import PROJECT_ROOT, episodes_dir_for, read_json

log = logging.getLogger("reco.vignettes")

DOSSIER: Path = PROJECT_ROOT / "public" / "vignettes"
_YOUTUBE_ID = re.compile(r"[?&]v=([\w-]+)")
_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

Telecharger = Callable[[str], bytes]


def youtube_id(episode: Mapping[str, Any]) -> str | None:
    trouve = _YOUTUBE_ID.search(episode.get("youtubeUrl") or "")
    return trouve.group(1) if trouve else None


def vignettes(episode: Mapping[str, Any]) -> dict[str, str]:
    """Nom de fichier -> adresse d'origine, pour un episode. Vide sans image."""
    ident = youtube_id(episode)
    if ident:
        return {
            f"yt-{ident}-mq.jpg": f"https://i.ytimg.com/vi/{ident}/mqdefault.jpg",
            f"yt-{ident}-hq.jpg": f"https://i.ytimg.com/vi/{ident}/hqdefault.jpg",
        }
    image = episode.get("imageUrl")
    if not image:
        return {}
    extension = PurePosixPath(urlparse(image).path).suffix.lower()
    if extension not in _EXTENSIONS:
        extension = ".jpg"
    return {f"ep-{hashlib.sha1(image.encode(), usedforsecurity=False).hexdigest()[:12]}{extension}": image}


def _telecharger(url: str) -> bytes:
    import requests
    reponse = requests.get(url, timeout=30)
    reponse.raise_for_status()
    return reponse.content


def recuperer(episode: Mapping[str, Any], *, dossier: Path = DOSSIER,
              telecharger: Telecharger = _telecharger) -> list[Path]:
    """Telecharge les vignettes absentes d'un episode ; rend les fichiers ecrits."""
    ecrits = []
    for nom, url in vignettes(episode).items():
        cible = dossier / nom
        if cible.exists():
            continue
        contenu = telecharger(url)
        if not contenu:
            raise ValueError(f"image vide : {url}")
        dossier.mkdir(parents=True, exist_ok=True)
        temporaire = cible.with_name(cible.name + ".tmp")
        temporaire.write_bytes(contenu)
        temporaire.replace(cible)
        ecrits.append(cible)
    return ecrits


def fichiers(episode: Mapping[str, Any], *, dossier: Path = DOSSIER) -> list[Path]:
    """Les vignettes de l'episode deja presentes sur le disque."""
    return [dossier / nom for nom in vignettes(episode) if (dossier / nom).exists()]


def recuperer_tout(episodes: Iterable[Mapping[str, Any]], *, dossier: Path = DOSSIER,
                   telecharger: Telecharger = _telecharger) -> tuple[int, list[str]]:
    """Toutes les vignettes manquantes ; une panne n'arrete pas les suivantes."""
    ecrits, pannes = 0, []
    for episode in episodes:
        try:
            ecrits += len(recuperer(episode, dossier=dossier, telecharger=telecharger))
        except Exception as exc:  # noqa: BLE001 — un episode en panne n'arrete pas les autres.
            pannes.append(f"{episode.get('guid')}: {type(exc).__name__}: {str(exc)[:120]}")
    return ecrits, pannes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    episodes = [read_json(p) for p in sorted(episodes_dir_for(args.source).glob("*.json"))]
    ecrits, pannes = recuperer_tout(episodes)
    log.info("%d vignette(s) telechargee(s), %d panne(s)", ecrits, len(pannes))
    for panne in pannes:
        log.warning("  %s", panne)
    return 1 if pannes else 0


if __name__ == "__main__":
    sys.exit(main())
