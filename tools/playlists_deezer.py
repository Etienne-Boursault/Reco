"""
playlists_deezer.py — equivalents Deezer des playlists Spotify « Un Bon Moment ».

Les playlists Deezer du compte « Une Bonne Reco » reprennent, titre pour titre et
dans le meme ordre, les playlists Spotify (voir playlists_musique.py). Le lien
entre les deux est l'ISRC, le code de l'enregistrement : le lecteur Spotify le
donne (`__spIsrc` dans reseaux_episode_ui.js), l'API publique de Deezer le
resout (`/track/isrc:<code>`). Un ISRC inconnu de Deezer se rattrape par la
recherche (meme chanson, duree la plus proche), a verifier a la main.

Usage, dans le deroule de reseaux_episode.py :
  python tools/playlists_deezer.py <plan.json> "<id_spotify>=<ISRC> ..."
remplit la partie `deezer` du plan (titres a ajouter, playlist par playlist).
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playlists_musique import Embed, meme_chanson, norm

ETAT = Path(__file__).resolve().parent / "data" / "playlists_deezer.json"
ECART_MAX_MS = 5000


def choisir(titre: str, artistes: str, duree_ms: int,
            candidats: list[dict[str, Any]]) -> tuple[int | None, str]:
    """Meilleur candidat de la recherche Deezer pour une chanson ; « doute » sauf accord parfait."""
    cle = meme_chanson(titre, artistes)
    memes = [c for c in candidats if meme_chanson(c["title"], c["artist"]["name"]) == cle]
    if not memes:
        return None, "absent"
    meilleur = min(memes, key=lambda c: abs(c.get("duration", 0) * 1000 - duree_ms))
    ecart = abs(meilleur.get("duration", 0) * 1000 - duree_ms)
    exact = norm(meilleur["title"]) == norm(titre) and ecart <= ECART_MAX_MS
    return meilleur["id"], "recherche" if exact else "doute"


class Deezer:
    """API publique de Deezer, en lecture seule."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    def _get(self, url: str, **params: Any) -> dict[str, Any]:
        for essai in range(4):
            data = self.session.get(url, params=params, timeout=20).json()
            if "error" not in data or data["error"].get("code") != 4:  # 4 = quota
                time.sleep(0.12)
                return data
            time.sleep(2 + 3 * essai)
        return {}

    def par_isrc(self, isrc: str) -> int | None:
        return self._get(f"https://api.deezer.com/track/isrc:{isrc}").get("id")

    def chercher(self, titre: str, artiste: str) -> list[dict[str, Any]]:
        # La recherche avancee (artist:"…" track:"…") ne renvoie plus rien.
        return self._get("https://api.deezer.com/search", q=f"{artiste} {titre}", limit=15).get("data", [])

    def pistes(self, playlist_id: int) -> list[int]:
        ids, url = [], f"https://api.deezer.com/playlist/{playlist_id}/tracks?limit=100"
        while url:
            data = self._get(url)
            ids += [t["id"] for t in data.get("data", [])]
            url = data.get("next")
        return ids


def correspondance(tid: str, isrc: str | None, embed: Embed, deezer: Deezer) -> tuple[int | None, str]:
    """Titre Deezer d'un titre Spotify : par l'ISRC (« isrc »), sinon par la recherche."""
    if isrc and (trouve := deezer.par_isrc(isrc)):
        return trouve, "isrc"
    titre, artistes = embed.titre_artiste(tid)
    premier = artistes.split(",")[0].strip()
    candidats = deezer.chercher(titre, premier)
    court = re.sub(r"\(.*?\)|\[.*?\]|\s-\s.*$", "", titre).strip()
    if court != titre:
        candidats += deezer.chercher(court, premier)
    return choisir(titre, artistes, embed.duree(tid), candidats)


def lire_isrc(texte: str) -> dict[str, str]:
    """« id=ISRC id=ISRC … » (sortie de `__spIsrc`) -> {id: ISRC} ; « id=- » si inconnu."""
    paires = (m.split("=", 1) for m in texte.split() if "=" in m)
    return {tid: isrc for tid, isrc in paires if isrc and isrc != "-"}


def remplir_plan(plan: dict[str, Any], isrc: dict[str, str], embed: Embed, deezer: Deezer) -> list[str]:
    """Ajoute au plan les titres Deezer de chaque playlist ; renvoie ce qui est a verifier."""
    etat = json.loads(ETAT.read_text(encoding="utf-8"))["playlists"]
    trouves: dict[str, tuple[int | None, str]] = {}
    for tid in dict.fromkeys(t for p in plan["spotify"].values() for t in p["ajouts"]):
        trouves[tid] = correspondance(tid, isrc.get(tid), embed, deezer)
    plan["deezer"] = {}
    for nom, p in plan["spotify"].items():
        ids = [trouves[t][0] for t in p["ajouts"] if trouves[t][0]]
        plan["deezer"][nom] = {"id": etat[nom]["id"], "ajouts": list(dict.fromkeys(ids))}
    return [f"{tid} {embed.titre_artiste(tid)} -> {dz} ({cert})"
            for tid, (dz, cert) in trouves.items() if cert != "isrc"]


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    chemin = Path(sys.argv[1])
    plan = json.loads(chemin.read_text(encoding="utf-8"))
    a_verifier = remplir_plan(plan, lire_isrc(sys.argv[2]), Embed(), Deezer())
    chemin.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for nom, p in plan["deezer"].items():
        print(f"{nom} : {len(p['ajouts'])} titre(s) Deezer a ajouter")
    for ligne in a_verifier:
        print("  A VERIFIER :", ligne)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
