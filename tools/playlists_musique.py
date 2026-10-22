"""
playlists_musique.py — contenu des playlists Spotify « Un Bon Moment ».

CE QUE FAIT CET OUTIL
---------------------
Calcule, a partir du corpus, la liste ordonnee des titres de chaque playlist
du compte Spotify « Une Bonne Reco » : une par saison, une pour les episodes
d'avant la numerotation (2020-2024), une qui cumule tout. Ordre des episodes,
du plus ancien au plus recent, pour que chaque nouvel episode s'ajoute a la
fin : le lecteur web n'insere jamais ailleurs.

Une reco musicale validee donne : son titre (morceau), les 3 titres phares de
l'artiste (artiste), ou 3 titres de l'album, ceux du top de l'artiste d'abord.
Les titres viennent des pages publiques `open.spotify.com/embed/...` : l'API
repond 403 depuis la fin de l'abonnement Premium du proprietaire de l'app.

MISE A JOUR
-----------
`python tools/playlists_musique.py` compare au dernier etat publie
(`tools/data/playlists_spotify.json`) et affiche, par playlist, les titres a
ajouter en fin de liste. Les ajouts se font dans le lecteur web, connecte au
compte, avec `tools/playlists_musique_ui.js`. Une fois faits :
`--enregistrer` met a jour l'etat publie. Si un titre doit s'inserer au milieu
(lien pose apres coup sur un vieil episode), l'outil le dit : il faut alors
vider puis remplir la playlist (`__vider`, puis `__lotSp`).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import EPISODES_DIR, ITEMS_DIR, MENTIONS_DIR, RECOS_DIR

SOURCE = "un-bon-moment"
ETAT = Path(__file__).resolve().parent / "data" / "playlists_spotify.json"
TYPES = ("musique", "album", "artiste")
# Humoristes dont Spotify heberge les spectacles : un lien Spotify ne suffit pas
# a faire d'une fiche « artiste » une reco musicale.
EXCLUS = {"162d3378", "d432f454", "af1553d5"}  # Greer Barnes, Richard Pryor, Anthony Jeselnik
AVANT_SAISONS = "Saisons 1 à 4 (2020-2024)"
TOUT = "Toutes les recos musicales"
FORME = re.compile(r"open\.spotify\.com/(?:intl-[a-z]+/)?(track|album|artist|show)/([A-Za-z0-9]+)")


def _lire(dossier: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in (dossier / SOURCE).glob("*.json")]


def norm(texte: str | None) -> str:
    s = unicodedata.normalize("NFD", texte or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def forme(url: str) -> tuple[str | None, str | None]:
    m = FORME.search(url or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def nom_playlist(saison: int | None) -> str:
    return f"Saison {saison}" if saison else AVANT_SAISONS


def entrees() -> list[dict[str, Any]]:
    """Une entree par fiche et par playlist de saison, la plus ancienne mention d'abord."""
    episodes = {e["guid"]: e for e in _lire(EPISODES_DIR)}
    items = {i["id"]: i for i in _lire(ITEMS_DIR)}
    recos = {r["id"]: r for r in _lire(RECOS_DIR)}
    retenues: dict[tuple[str, str], dict[str, Any]] = {}
    for m in _lire(MENTIONS_DIR):
        item = items.get(m["itemId"])
        if m.get("status") != "validated" or m.get("kind") == "citation" or not item:
            continue
        if m["itemId"] in EXCLUS or not set(item.get("types", [])) & set(TYPES):
            continue
        url = next((lien.get("url", "") for lien in recos.get(m["id"], {}).get("links") or []
                    if "open.spotify.com" in lien.get("url", "")), None)
        if not url:
            continue
        ep = episodes.get(m["sourceRef"]["episodeGuid"], {})
        e = {"item": item["id"], "titre": item["title"], "url": url, "date": ep.get("date") or "",
             "playlist": nom_playlist(ep.get("season")),
             "type": next(t for t in TYPES if t in item["types"])}
        cle = (e["playlist"], e["item"])
        if cle not in retenues or e["date"] < retenues[cle]["date"]:
            retenues[cle] = e
    return sorted(retenues.values(), key=lambda e: (e["date"], e["titre"]))


class Embed:
    """Lecture des pages publiques de Spotify, avec cache par execution."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = "Mozilla/5.0"
        self.cache: dict[tuple[str, str], list[tuple[str, str]]] = {}

    def pistes(self, genre: str, sid: str) -> list[tuple[str, str]]:
        if (genre, sid) not in self.cache:
            page = self.session.get(f"https://open.spotify.com/embed/{genre}/{sid}", timeout=20).text
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page)
            ent = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"] if m else {}
            self.cache[(genre, sid)] = [
                (t["uri"].split(":")[-1], t["title"]) for t in ent.get("trackList", [])
                if t.get("isPlayable", True) and t.get("uri", "").startswith("spotify:track:")]
            time.sleep(0.3)
        return self.cache[(genre, sid)]

    def artiste_de_album(self, sid: str) -> str | None:
        page = self.session.get(f"https://open.spotify.com/album/{sid}", timeout=20).text
        m = re.search(r'name="music:musician" content="https://open\.spotify\.com/artist/([A-Za-z0-9]+)', page)
        return m.group(1) if m else None


def titres(e: dict[str, Any], embed: Embed) -> list[str]:
    genre, sid = forme(e["url"])
    if genre == "track":
        return [sid]
    if genre == "artist":
        return [i for i, _ in embed.pistes("artist", sid)[:3]]
    if genre != "album":
        return []
    album = embed.pistes("album", sid)
    if e["type"] == "musique":
        cible = re.sub(r"^(l|le|la|les) ", "", norm(e["titre"]))
        meme = [i for i, t in album if norm(t) == norm(e["titre"])] \
            or [i for i, t in album if cible and cible in norm(t)]
        if meme:
            return meme[:1]
    artiste = embed.artiste_de_album(sid)
    top = [i for i, _ in embed.pistes("artist", artiste)] if artiste else []
    ids = [i for i, _ in album]
    choisis = [i for i in top if i in ids][:3]
    return choisis + [i for i in ids if i not in choisis][:3 - len(choisis)]


def playlists(liste: list[dict[str, Any]], embed: Embed) -> dict[str, list[str]]:
    sortie: dict[str, list[str]] = {TOUT: []}
    for e in liste:
        for cle in (e["playlist"], TOUT):
            cible = sortie.setdefault(cle, [])
            cible.extend(i for i in titres(e, embed) if i not in cible)
    return sortie


def a_ajouter(publie: list[str], voulu: list[str]) -> tuple[list[str], bool]:
    """Titres a ajouter en fin de liste, et si l'ordre publie reste un prefixe du voulu."""
    reste = [i for i in voulu if i in publie]
    return [i for i in voulu if i not in publie], reste == publie[:len(reste)] == voulu[:len(reste)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--enregistrer", action="store_true", help="ecrire l'etat publie")
    args = parser.parse_args()
    etat = json.loads(ETAT.read_text(encoding="utf-8"))
    voulu = playlists(entrees(), Embed())
    for nom, ids in voulu.items():
        publie = etat["playlists"].get(nom, {}).get("titres", [])
        nouveaux, en_fin = a_ajouter(publie, ids)
        retires = [i for i in publie if i not in ids]
        print(f"{nom} : {len(publie)} -> {len(ids)} titres, {len(nouveaux)} a ajouter"
              + ("" if en_fin and not retires else " — RECONSTRUCTION (ordre ou retraits)"))
        if nouveaux:
            print("  " + json.dumps(nouveaux))
        if args.enregistrer:
            etat["playlists"].setdefault(nom, {})["titres"] = ids
    if args.enregistrer:
        ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
