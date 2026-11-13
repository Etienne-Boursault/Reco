"""
carrousel_episode.py — carrousel Instagram/Threads d'un episode, en PNG 1080x1350.

Couverture, une page par reco, page de fin, chacune avec son visuel depuis le
2026-11-13 (modele valide par Etienne sur le canevas Design « Carrousel avec
visuels », mise en page dans `carrousel_scenes.py`). `episode.json` (produit
par reseaux_episode.py, puis relu a la main) donne pour chaque page son texte
et l'adresse de son image (`image`, une adresse ou une liste de deux, a
changer ou retirer a la relecture ; `mise` force la mise en scene) ; les
images sont telechargees dans `images/`, Edge sans interface rend chaque page
en PNG. A cote : les legendes Instagram (« lien en bio ») et Threads (lien
direct, 500 caracteres au plus) et les textes alternatifs.

Usage : python tools/carrousel_episode.py <dossier contenant episode.json>
"""
from __future__ import annotations

import json
import logging
import mimetypes
import shutil
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
NAVIGATEUR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
Telecharger = Callable[[str, Path], "Path | None"]


def ecrire(dst: Path, helmet: str, corps: str) -> None:
    dst.write_text(
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">' + helmet
        + "<style>html,body{margin:0;padding:0;overflow:hidden;background:#0e0e10}</style></head><body>"
        + corps + "</body></html>", encoding="utf-8")


def telecharger(url: str, chemin: Path, session: Any = None) -> Path | None:
    """Telecharge une image vers `chemin` (extension d'apres le type rendu) ; None en cas d'echec."""
    try:
        reponse = (session or requests).get(url, headers=NAVIGATEUR, timeout=30)
        reponse.raise_for_status()
    except (OSError, ValueError) as exc:  # requests.RequestException derive d'OSError
        log.warning("image du carrousel : telechargement en echec pour %s (%s : %s)", url, type(exc).__name__, exc)
        return None
    type_ = (reponse.headers.get("content-type") or "").split(";")[0]
    suffixe = mimetypes.guess_extension(type_) or Path(urlparse(url).path).suffix or ".jpg"
    chemin = chemin.with_suffix(".jpg" if suffixe == ".jpe" else suffixe)
    chemin.write_bytes(reponse.content)
    return chemin


def _images(r: dict[str, Any], dossier: Path, rang: int, tel: Telecharger) -> list[tuple[str, Path]]:
    adresses = r.get("image") or []
    adresses = [adresses] if isinstance(adresses, str) else adresses
    faites = [(url, tel(url, dossier / f"{rang:02d}-{i}")) for i, url in enumerate(adresses)]
    return [(url, chemin) for url, chemin in faites if chemin]


def pages(ep: dict[str, Any], sortie: Path, telecharger: Telecharger | None = None) -> list[Path]:
    """Ecrit les pages HTML du carrousel (images comprises) et renvoie leurs chemins, dans l'ordre."""
    tel = telecharger or globals()["telecharger"]
    dossier = sortie / "images"
    dossier.mkdir(parents=True, exist_ok=True)
    recos, total, utilisees, faites = ep["recos"], len(ep["recos"]), [], []
    vignette = tel(ep["couverture"], dossier / "00-couverture") if ep.get("couverture") else None
    if vignette:
        utilisees.append(ep["couverture"])
    faites.append(sortie / "01-couverture.html")
    ecrire(faites[-1], cs.HEAD, cs.couverture(ep, total, vignette.resolve().as_uri() if vignette else None))
    for rang, r in enumerate(recos, 1):
        images = _images(r, dossier, rang, tel)
        utilisees += [url for url, _ in images]
        tailles = [Image.open(chemin).size for _, chemin in images]
        calculee = ci.mise_en_scene(r["type"], tailles)
        # Une mise forcee dans episode.json ne vaut que si ses images sont la.
        mise = r["mise"] if r.get("mise") and tailles and (r["mise"] == "double") == (len(tailles) > 1) else calculee
        alts = [(chemin.resolve().as_uri(), f"Visuel de « {r['titre']} »") for _, chemin in images]
        faites.append(sortie / f"{rang + 1:02d}-reco.html")
        ecrire(faites[-1], cs.HEAD, cs.page_reco(r, rang, total, alts, mise))
    faites.append(sortie / f"{total + 2:02d}-fin.html")
    ecrire(faites[-1], cs.HEAD, cs.fin(ep, total, ci.credits(utilisees)))
    return faites


def textes(ep: dict[str, Any]) -> dict[str, Any]:
    """Legendes Instagram et Threads, et un texte alternatif par image."""
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
