"""
reseaux_episode.py — prepare la publication d'un episode sur les reseaux.

Apres la relecture d'un episode (ses recos validees sont dans le depot), une
seule commande prepare tout ce qui part ailleurs que sur le site :

  python tools/reseaux_episode.py S6-E06 [--sortie DOSSIER]

Dans DOSSIER (par defaut Images/unebonnere.co/<date>-S6E06) :
- `episode.json` : le carrousel Instagram/Threads (une page par mention
  validee), a relire avant `python tools/carrousel_episode.py DOSSIER` ;
- `plan.json` : les titres a ajouter aux playlists Spotify (puis Deezer, via
  playlists_deezer.py) et les oeuvres a ajouter aux listes SensCritique.

Les ajouts se font dans le navigateur avec tools/reseaux_episode_ui.js ; le
deroule complet est dans docs/reseaux-episode.md. Une fois tout publie :

  python tools/reseaux_episode.py --enregistrer DOSSIER/plan.json

met a jour les etats (tools/data/playlists_*.json, senscritique.json).
Le commentaire YouTube, lui, part tout seul depuis venus.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import playlists_deezer
import playlists_musique as pm

DATA = Path(__file__).resolve().parent / "data"
SENSCRITIQUE = DATA / "senscritique.json"
LIBELLES = {
    "film": "Film", "serie": "Série", "livre": "Livre", "bd": "BD", "musique": "Musique",
    "album": "Album", "podcast": "Podcast", "jeu": "Jeu", "spectacle": "Spectacle", "lieu": "Lieu",
    "artiste": "Artiste", "video": "Vidéo", "chaine": "Chaîne YouTube", "application": "Application",
    "autre": "Autre",
}
CODE = re.compile(r"^S(\d+)-?E(\d+)$", re.IGNORECASE)


def typo(texte: str | None) -> str:
    """Apostrophes typographiques, comme sur les visuels deja publies."""
    return (texte or "").replace("'", "’").strip()


def moment(horodatage: str | None) -> str:
    """« 00:01:10 » -> « 1:10 », « 01:15:27 » -> « 1:15:27 »."""
    if not horodatage:
        return ""
    h, m, s = (int(x) for x in ([0, 0] + horodatage.split(":"))[-3:])
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def trouver_episode(code: str, episodes: list[dict[str, Any]]) -> dict[str, Any]:
    m = CODE.match(code)
    for ep in episodes:
        if ep["guid"] == code or (m and ep.get("season") == int(m[1]) and ep.get("number") == int(m[2])):
            return ep
    raise SystemExit(f"episode introuvable : {code}")


def mentions_validees(ep: dict[str, Any], mentions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    liste = [m for m in mentions
             if m["sourceRef"]["episodeGuid"] == ep["guid"] and m.get("status") == "validated"]
    return sorted(liste, key=lambda m: m["sourceRef"].get("timestamp") or "")


def createur(item: dict[str, Any], reco: dict[str, Any]) -> str:
    """Ligne sous le titre : le createur, sinon la plateforme ou regarder. Un lieu n'a pas de createur."""
    if "lieu" in item.get("types", []):
        return ""
    if item.get("creator"):
        return typo(item["creator"])
    plateforme = next((p["label"] for p in reco.get("watchProviders") or [] if p.get("ethics") != "avoid"), None)
    return f"Sur {plateforme}" if plateforme else ""


def carrousel(ep: dict[str, Any], mentions: list[dict[str, Any]], items: dict[str, dict[str, Any]],
              recos: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Brouillon de `episode.json` : a relire (citations a raccourcir, « qui » manquants)."""
    pages = []
    for m in mentions_validees(ep, mentions):
        item, reco = items[m["itemId"]], recos.get(m["id"], {})
        pages.append({
            "type": LIBELLES.get((item.get("types") or ["autre"])[0], "Autre"),
            "titre": typo(item["title"]),
            "createur": createur(item, reco),
            "citation": typo(m.get("quote")),
            "qui": m.get("recommendedBy") or "",
            "moment": moment(m["sourceRef"].get("timestamp")),
        })
    return {
        "numero": f"S{ep['season']} · E{ep['number']:02d}",
        "titre": typo(re.sub(r"\s*\(Un Bon Moment, S\d+-E\d+\)\s*$", "", ep["title"])),
        "invites": ep.get("guestsParsed") or ep.get("guests") or [],
        "lien": f"https://unebonnere.co/un-bon-moment/episode/{ep['guid']}/",
        "recos": pages,
    }


def senscritique(ep: dict[str, Any], mentions: list[dict[str, Any]], items: dict[str, dict[str, Any]],
                 etat: dict[str, Any]) -> dict[str, Any]:
    """Oeuvres de l'episode pas encore traitees, par liste (les citations n'y vont pas)."""
    sortie = {}
    for univers, liste in etat["listes"].items():
        oeuvres = []
        for m in mentions_validees(ep, mentions):
            item = items[m["itemId"]]
            if m.get("kind") == "citation" or univers not in item.get("types", []):
                continue
            if item["id"] in liste["traitees"] or any(o["fiche"] == item["id"] for o in oeuvres):
                continue
            oeuvres.append({"fiche": item["id"], "titre": item["title"], "annee": item.get("year"),
                            "createur": item.get("creator") or ""})
        sortie[univers] = {"liste": liste["id"], "oeuvres": oeuvres}
    return sortie


def musique(voulu: dict[str, list[str]], etat_sp: dict[str, Any],
            cle: Callable[[str], str]) -> tuple[dict[str, Any], list[str]]:
    """Titres de l'episode a ajouter en fin de chaque playlist, sans doublon de chanson.

    `voulu` ne couvre que l'episode publie : les titres phares d'un artiste
    changent, recalculer les anciens episodes deplacerait des titres publies.
    """
    plan, alertes = {}, []
    for nom, ids in voulu.items():
        if nom not in etat_sp:
            alertes.append(f"playlist « {nom} » absente : la creer sur Spotify et Deezer, puis l'ajouter aux etats")
            continue
        publies = etat_sp[nom]["titres"]
        chansons = {cle(i) for i in publies}
        ajouts = []
        for i in ids:
            if i not in publies and cle(i) not in chansons:
                ajouts.append(i)
                chansons.add(cle(i))
        plan[nom] = {"id": etat_sp[nom]["id"], "ajouts": ajouts}
    return plan, alertes


def preparer(code: str, sortie: Path | None) -> int:
    episodes = pm._lire(pm.EPISODES_DIR)
    ep = trouver_episode(code, episodes)
    mentions = pm._lire(pm.MENTIONS_DIR)
    items = {i["id"]: i for i in pm._lire(pm.ITEMS_DIR)}
    recos = {r["id"]: r for r in pm._lire(pm.RECOS_DIR)}
    sortie = sortie or Path.home() / "Pictures" / "unebonnere.co" / f"{ep['date']}-S{ep['season']}E{ep['number']:02d}"
    sortie.mkdir(parents=True, exist_ok=True)

    brouillon = carrousel(ep, mentions, items, recos)
    (sortie / "episode.json").write_text(json.dumps(brouillon, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    etat_sp = json.loads(pm.ETAT.read_text(encoding="utf-8"))["playlists"]
    embed = pm.Embed()
    du_jour = [e for e in pm.entrees() if e["guid"] == ep["guid"]]
    spotify, alertes = musique(pm.playlists(du_jour, embed), etat_sp,
                               lambda i: pm.meme_chanson(*embed.titre_artiste(i)))
    sc = senscritique(ep, mentions, items, json.loads(SENSCRITIQUE.read_text(encoding="utf-8")))
    plan = {"episode": {"guid": ep["guid"], "code": f"S{ep['season']}-E{ep['number']:02d}", "titre": ep["title"]},
            "spotify": spotify, "senscritique": sc, "alertes": alertes}
    (sortie / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"{plan['episode']['code']} — {ep['title']}\n{sortie}")
    print(f"Carrousel : {len(brouillon['recos'])} pages de reco (episode.json, a relire)")
    for nom, p in spotify.items():
        print(f"Spotify {nom} : {len(p['ajouts'])} titre(s) a ajouter")
    for univers, s in sc.items():
        print(f"SensCritique {univers} : {[o['titre'] for o in s['oeuvres']]}")
    for a in alertes:
        print("ALERTE :", a)
    sans_qui = [r["titre"] for r in brouillon["recos"] if not r["qui"]]
    if sans_qui:
        print("Sans « qui » (a completer dans episode.json) :", sans_qui)
    return 0


def enregistrer(chemin: Path) -> int:
    """Reporte un plan publie dans les etats ; Deezer est relu en ligne, ce qui fait foi."""
    plan = json.loads(chemin.read_text(encoding="utf-8"))
    etat_sp = json.loads(pm.ETAT.read_text(encoding="utf-8"))
    for nom, p in plan["spotify"].items():
        titres = etat_sp["playlists"][nom]["titres"]
        titres.extend(i for i in p["ajouts"] if i not in titres)
    pm.ETAT.write_text(json.dumps(etat_sp, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    etat_dz = json.loads(playlists_deezer.ETAT.read_text(encoding="utf-8"))
    deezer = playlists_deezer.Deezer()
    for p in etat_dz["playlists"].values():
        p["titres"] = deezer.pistes(p["id"])
    playlists_deezer.ETAT.write_text(json.dumps(etat_dz, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    etat_sc = json.loads(SENSCRITIQUE.read_text(encoding="utf-8"))
    for univers, s in plan["senscritique"].items():
        traitees = etat_sc["listes"][univers]["traitees"]
        traitees.extend(o["fiche"] for o in s["oeuvres"] if o["fiche"] not in traitees)
        traitees.sort()
    SENSCRITIQUE.write_text(json.dumps(etat_sc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for nom, p in etat_sp["playlists"].items():
        dz = len(etat_dz["playlists"].get(nom, {}).get("titres", []))
        print(f"{nom} : Spotify {len(p['titres'])}, Deezer {dz}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("episode", nargs="?", help="S6-E06 ou guid")
    parser.add_argument("--sortie", type=Path)
    parser.add_argument("--enregistrer", type=Path, metavar="PLAN", help="reporter un plan publie dans les etats")
    args = parser.parse_args()
    if args.enregistrer:
        return enregistrer(args.enregistrer)
    if not args.episode:
        parser.error("episode manquant")
    return preparer(args.episode, args.sortie)


if __name__ == "__main__":
    raise SystemExit(main())
