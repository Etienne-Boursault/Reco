"""
carrousel_episode.py — carrousel Instagram/Threads d'un episode, en PNG 1080x1350.

Les gabarits viennent du canevas Design (`tools/carrousel/*.dc.html`) :
couverture, une page par reco, page de fin. `episode.json` (produit par
reseaux_episode.py, puis relu a la main) les remplit ; Edge sans interface
rend chaque page en PNG. A cote : les legendes Instagram (« lien en bio ») et
Threads (lien direct, 500 caracteres au plus) et les textes alternatifs.

Usage : python tools/carrousel_episode.py <dossier contenant episode.json>
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

GABARITS = Path(__file__).resolve().parent / "carrousel"
ACCENT = "#ffd23f"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
EMOJIS = {"Série": "📺", "Film": "🎬", "Spectacle": "🎭", "Livre": "📚", "BD": "💭", "Musique": "🎵",
          "Album": "🎵", "Artiste": "🎤", "Chaîne YouTube": "🎤", "Podcast": "🎙️", "Jeu": "🎮",
          "Lieu": "📍", "Vidéo": "📹", "Application": "📱"}
LIMITE_THREADS = 500


def morceaux(src: Path) -> tuple[str, str]:
    texte = src.read_text(encoding="utf-8")
    helmet = re.search(r"<helmet>(.*?)</helmet>", texte, re.DOTALL).group(1)
    corps = re.search(r"</helmet>(.*?)</x-dc>", texte, re.DOTALL).group(1)
    return helmet, corps


def remplir(corps: str, valeurs: dict[str, Any]) -> str:
    def boucle(m: re.Match[str]) -> str:
        liste, var, tpl = valeurs[m.group(1)], m.group(2), m.group(3)
        return "".join(
            re.sub(r"\{\{" + var + r"\.(\w+)\}\}", lambda k, e=e: html.escape(str(e[k.group(1)])), tpl)
            for e in liste)

    corps = re.sub(r'<sc-for list="\{\{(\w+)\}\}" as="(\w+)"[^>]*>(.*?)</sc-for>', boucle, corps, flags=re.DOTALL)
    corps = re.sub(r"\{\{(\w+)\}\}", lambda m: html.escape(str(valeurs[m.group(1)])), corps)
    if "{{" in corps:
        raise SystemExit(f"gabarit non resolu : {re.findall(r'{{[^}]*}}', corps)}")
    return corps


def taille_titre(titre: str) -> int:
    """Le gabarit vise 190 px ; on reduit pour tenir en deux lignes de Bebas Neue."""
    mots = max(len(m) for m in titre.split())
    if len(titre) <= 18 and mots <= 9:
        return 190
    if len(titre) <= 26 and mots <= 11:
        return 160
    return 130


def ecrire(dst: Path, helmet: str, corps: str) -> None:
    dst.write_text(
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">' + helmet
        + "<style>html,body{margin:0;padding:0;overflow:hidden;background:#0e0e10}</style></head><body>"
        + corps + "</body></html>", encoding="utf-8")


def pages(ep: dict[str, Any], sortie: Path) -> list[Path]:
    """Ecrit les pages HTML du carrousel et renvoie leurs chemins, dans l'ordre."""
    recos, faites = ep["recos"], []
    total = len(recos)
    helmet, corps = morceaux(GABARITS / "EpCouverture.dc.html")
    faites.append(sortie / "01-couverture.html")
    ecrire(faites[-1], helmet, remplir(corps, {
        "accent": ACCENT, "numero": ep["numero"], "titre": ep["titre"], "nbRecos": total,
        "invites": [{"nom": n} for n in ep["invites"]]}))
    helmet, corps = morceaux(GABARITS / "EpReco.dc.html")
    for rang, r in enumerate(recos, 1):
        page = remplir(corps, {"accent": ACCENT, "rang": rang, "total": total, **r})
        page = page.replace("font-size: 190px", f"font-size: {taille_titre(r['titre'])}px", 1)
        faites.append(sortie / f"{rang + 1:02d}-reco.html")
        ecrire(faites[-1], helmet, page)
    helmet, corps = morceaux(GABARITS / "EpFin.dc.html")
    faites.append(sortie / f"{total + 2:02d}-fin.html")
    ecrire(faites[-1], helmet, remplir(corps, {"accent": ACCENT, "numero": ep["numero"], "nbRecos": total}))
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


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    dossier = Path(sys.argv[1])
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
