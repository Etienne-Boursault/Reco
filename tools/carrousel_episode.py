"""
carrousel_episode.py — carrousel Instagram/Threads d'un épisode, en PNG 1080×1350.

Couverture, une page par reco, page de fin, chacune avec son visuel depuis le
2026-11-13 (modèle validé par Étienne sur le canevas Design « Carrousel avec
visuels », mise en page dans `carrousel_scenes.py`). `episode.json` (produit
par reseaux_episode.py, puis relu à la main) donne pour chaque page son texte
et l'adresse de son image (`image`, une adresse ou une liste de deux, à
changer ou retirer à la relecture ; `mise` force la mise en scène) ; les
images sont téléchargées dans `images/`, Edge sans interface rend chaque page
en PNG. À côté : les légendes Instagram (« lien en bio ») et Threads (lien
direct, 500 caractères au plus) et les textes alternatifs.

Usage : python tools/carrousel_episode.py <dossier contenant episode.json>
"""
from __future__ import annotations

import json
import logging
import mimetypes
import shutil
import struct
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carrousel_images as ci
import carrousel_scenes as cs

log = logging.getLogger("reco")
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
EMOJIS = {"Série": "📺", "Film": "🎬", "Spectacle": "🎭", "Livre": "📚", "BD": "💭", "Musique": "🎵",
          "Album": "🎵", "Artiste": "🎤", "Chaîne YouTube": "🎤", "Podcast": "🎙️", "Jeu": "🎮",
          "Lieu": "📍", "Vidéo": "📹", "Application": "📱"}
LIMITE_THREADS = 500
Telecharger = Callable[[str, Path], "Path | None"]
#: Orientations EXIF où l'image s'affiche tournée d'un quart de tour.
QUART_DE_TOUR = {5, 6, 7, 8}
#: Ce que Pillow lève sur un fichier qu'il ne sait pas lire (SVG, HTML, image tronquée ou géante).
ILLISIBLE = (OSError, ValueError, SyntaxError, struct.error, ZeroDivisionError, Image.DecompressionBombError)
#: YouTube rend une vignette grise de 120×90 quand une vidéo n'a pas la taille demandée.
SUBSTITUT_YOUTUBE = (120, 90)
INDEX = "index.json"


def ecrire(dst: Path, helmet: str, corps: str) -> None:
    dst.write_text(
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">' + helmet
        + "<style>html,body{margin:0;padding:0;overflow:hidden;background:#0e0e10}</style></head><body>"
        + corps + "</body></html>", encoding="utf-8")


def telecharger(url: str, chemin: Path, session: Any = None) -> Path | None:
    """Télécharge une image vers `chemin` (extension d'après le type rendu) ; None en cas d'échec."""
    try:
        reponse = (session or requests).get(url, headers=ci.entetes(url), timeout=30)
        reponse.raise_for_status()
    except (OSError, ValueError) as exc:  # requests.RequestException dérive d'OSError
        log.warning("image du carrousel : téléchargement en échec pour %s (%s : %s)", url, type(exc).__name__, exc)
        return None
    type_ = (reponse.headers.get("content-type") or "").split(";")[0]
    suffixe = mimetypes.guess_extension(type_) or Path(urlparse(url).path).suffix or ".jpg"
    chemin = chemin.with_suffix(".jpg" if suffixe == ".jpe" else suffixe)
    chemin.write_bytes(reponse.content)
    return chemin


def taille_affichee(chemin: Path) -> tuple[int, int] | None:
    """Largeur et hauteur telles que le navigateur affiche l'image (orientation EXIF comprise) ;
    None si Pillow ne sait pas la lire."""
    try:
        with Image.open(chemin) as image:
            largeur, hauteur = image.size
            tournee = image.getexif().get(274) in QUART_DE_TOUR
    except ILLISIBLE as exc:
        log.warning("image du carrousel : %s illisible (%s : %s), page sans cette image",
                    chemin.name, type(exc).__name__, exc)
        return None
    return (hauteur, largeur) if tournee else (largeur, hauteur)


def _avec_cache(tel: Telecharger, dossier: Path) -> Telecharger:
    """L'éditeur relance le rendu à chaque retouche d'episode.json : une image déjà
    téléchargée pour la même adresse ne l'est pas de nouveau (index `images/index.json`)."""
    chemin_index = dossier / INDEX
    try:
        index = json.loads(chemin_index.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {}

    def telecharger_une_fois(url: str, chemin: Path) -> Path | None:
        deja = dossier / index.get(url, "")
        if index.get(url) and deja.exists():
            return deja
        if fait := tel(url, chemin):
            index[url] = fait.name
            chemin_index.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        return fait
    return telecharger_une_fois


def _images(r: dict[str, Any], dossier: Path, rang: int, tel: Telecharger) -> list[tuple[str, Path, tuple[int, int]]]:
    adresses = r.get("image") or []
    # Une seule adresse, ou une liste ; un `null` dans la liste (image retirée) est ignoré.
    adresses = [a for a in ([adresses] if isinstance(adresses, str) else adresses) if a]
    lues = []
    for i, url in enumerate(adresses):
        if (chemin := tel(url, dossier / f"{rang:02d}-{i}")) and (taille := taille_affichee(chemin)):
            lues.append((url, chemin, taille))
    return lues


def _vignette(adresse: str | None, dossier: Path, tel: Telecharger) -> tuple[Path | None, str | None]:
    """Vignette de la couverture ; YouTube n'a pas de « maxresdefault » pour toutes les vidéos."""
    essais = [adresse] if adresse else []
    if adresse and "maxresdefault" in adresse:
        essais.append(adresse.replace("maxresdefault", "hqdefault"))
    for essai in essais:
        chemin = tel(essai, dossier / "00-couverture")
        if chemin and (taille := taille_affichee(chemin)) and taille != SUBSTITUT_YOUTUBE:
            return chemin, essai
    return None, None


def _mise(r: dict[str, Any], rang: int, tailles: list[tuple[int, int]], urls: list[str]) -> str:
    """Mise en scène calculée, sauf une mise forcée connue dont les images sont là ;
    une mise forcée inconnue ou incompatible est signalée à l'éditeur."""
    calculee, voulue = ci.mise_en_scene(r["type"], tailles, urls), r.get("mise")
    if not voulue:
        return calculee
    if voulue not in cs.MISES:
        log.warning("carrousel : page %d, mise « %s » inconnue (%s), « %s » à la place",
                    rang, voulue, ", ".join(sorted(cs.MISES)), calculee)
        return calculee
    if voulue == "sans" or (tailles and (voulue == "double") == (len(tailles) > 1)):
        return voulue
    log.warning("carrousel : page %d, mise « %s » ignorée (%d image(s) téléchargée(s)), « %s » à la place",
                rang, voulue, len(tailles), calculee)
    return calculee


def pages(ep: dict[str, Any], sortie: Path, tel: Telecharger | None = None) -> list[Path]:
    """Écrit les pages HTML du carrousel (images comprises) et renvoie leurs chemins, dans l'ordre."""
    dossier = sortie / "images"
    dossier.mkdir(parents=True, exist_ok=True)
    tel = _avec_cache(tel or telecharger, dossier)
    recos, total, utilisees, faites = ep["recos"], len(ep["recos"]), [], []
    vignette, adresse = _vignette(ep.get("couverture"), dossier, tel)
    if vignette:
        utilisees.append(adresse)
    faites.append(sortie / "01-couverture.html")
    ecrire(faites[-1], cs.HEAD, cs.couverture(ep, total, vignette.resolve().as_uri() if vignette else None))
    for rang, r in enumerate(recos, 1):
        images = _images(r, dossier, rang, tel)
        mise = _mise(r, rang, [taille for _, _, taille in images], [url for url, _, _ in images])
        montrees = [] if mise == "sans" else images[:2] if mise == "double" else images[:1]
        utilisees += [url for url, _, _ in montrees]  # seules les images montrées sont créditées
        if cs.trop_long(r, mise):
            log.warning("carrousel : page %d (« %s »), citation trop longue même au plus petit, "
                        "à raccourcir dans episode.json", rang, r["titre"])
        alts = [(chemin.resolve().as_uri(), f"Visuel de « {r['titre']} »") for _, chemin, _ in montrees]
        faites.append(sortie / f"{rang + 1:02d}-reco.html")
        ecrire(faites[-1], cs.HEAD, cs.page_reco(r, rang, total, alts, mise))
    faites.append(sortie / f"{total + 2:02d}-fin.html")
    ecrire(faites[-1], cs.HEAD, cs.fin(ep, total, ci.credits(utilisees)))
    return faites


def textes(ep: dict[str, Any]) -> dict[str, Any]:
    """Légendes Instagram et Threads, et un texte alternatif par image."""
    recos, n = ep["recos"], len(ep["recos"])
    groupes: dict[str, list[str]] = {}
    for r in recos:
        groupes.setdefault(EMOJIS.get(r["type"], "✨"), []).append(r["titre"])
    ordre = sorted(groupes, key=lambda e: -len(groupes[e]))  # a egalite, l'ordre d'apparition
    liste = "\n".join(f"{e} {', '.join(groupes[e])}" for e in ordre)
    numero = ep["numero"].replace(" ", "")
    tete = f"Les {n} recos d’Un Bon Moment {numero}, avec {' et '.join(ep['invites'])} 🎙️\n\n{liste}\n\n"
    pied = "Toutes les recos, au moment près et avec leurs liens"
    alts = [(f"Couverture : les {n} recos de l’épisode {numero} d’Un Bon Moment, « {ep['titre']} », "
             f"avec {' et '.join(ep['invites'])}.")]
    for i, r in enumerate(recos, 1):
        de = f" — {r['createur']}" if r["createur"] else ""
        qui = f" Reco de {r['qui']}, à {r['moment']}." if r["qui"] else f" À {r['moment']}."
        alts.append(f"Reco {i} sur {n}. {r['type']} : {r['titre']}{de}. « {r['citation']} »{qui}")
    alts.append(f"Fin : toutes les recos de l’épisode {numero} sur unebonnere.co.")
    return {
        "instagram": f"{tete}{pied} : lien en bio ⭐\n\nSite de fan, non officiel.",
        "threads": f"{tete}{pied} : {ep['lien']} ⭐\n\nSite de fan, non officiel.",
        "alts": alts,
    }


def rendre(page: Path) -> Path:
    png = page.with_suffix(".png")
    edge = shutil.which("msedge") or str(EDGE)
    subprocess.run([edge, "--headless", "--disable-gpu", "--hide-scrollbars", "--window-size=1080,1350",
                    "--virtual-time-budget=8000", f"--screenshot={png}", page.resolve().as_uri()],
                   check=True, capture_output=True, timeout=120)
    return png


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 2
    dossier = Path(argv[1])
    ep = json.loads((dossier / "episode.json").read_text(encoding="utf-8"))
    for page in pages(ep, dossier):
        print(rendre(page))
    t = textes(ep)
    (dossier / "legende-instagram.txt").write_text(t["instagram"] + "\n", encoding="utf-8")
    (dossier / "legende-threads.txt").write_text(t["threads"] + "\n", encoding="utf-8")
    (dossier / "alts.json").write_text(json.dumps(t["alts"], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if len(t["threads"]) > LIMITE_THREADS:
        print(f"ATTENTION : legende Threads de {len(t['threads'])} caracteres (max {LIMITE_THREADS}), a raccourcir")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
