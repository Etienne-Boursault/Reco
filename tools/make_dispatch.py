"""
make_dispatch.py — Génère la liste des épisodes à transcrire et la répartit
entre la machine principale (CPU, faster-whisper) et le portable (GPU,
whisper.cpp), proportionnellement à leur vitesse mesurée.

Sortie dans tools/dispatch/ :
  - episodes.json        : { guid: {youtubeUrl, title} } pour tous les pending
  - main_guids.txt       : guids assignés à la machine principale
  - laptop_guids.txt     : guids assignés au portable

Le serveur de fichiers (port 8001 sur tools/) les expose automatiquement.
"""

from __future__ import annotations

import json
from pathlib import Path

from common import list_episode_files, log, read_json, transcript_path_for

# Vitesses mesurées : main ~50 min/ép. (CPU small), portable ~27 min/ép. (GPU).
# Part du portable ≈ vitesse_portable / (vitesse_main + vitesse_portable) ≈ 64 %.
LAPTOP_SHARE = 0.64

DISPATCH_DIR = Path(__file__).resolve().parent / "dispatch"
SOURCE_ID = "un-bon-moment"


def main() -> None:
    pending = []
    for path in list_episode_files(SOURCE_ID):
        ep = read_json(path)
        guid = ep["guid"]
        # Déjà transcrit ? on saute.
        if transcript_path_for(SOURCE_ID, guid).exists():
            continue
        # Pas de vidéo YouTube ? on garde pour la machine principale en repli
        # (Acast) — pas envoyé au portable qui exige YouTube.
        if not ep.get("youtubeUrl"):
            continue
        pending.append({
            "guid": guid,
            "youtubeUrl": ep["youtubeUrl"],
            "title": ep.get("title", ""),
            "date": ep.get("date", ""),
        })

    # Plus récent en tête (les épisodes datés sans `date` finissent en fin).
    pending.sort(key=lambda e: e["date"] or "", reverse=True)

    total = len(pending)
    laptop_n = int(round(total * LAPTOP_SHARE))
    main_n = total - laptop_n

    # Pour équilibrer le ressenti, la main fait des épisodes RÉCENTS (que tu
    # verras vite arriver dans l'outil de relecture) ; le portable, plus
    # rapide, encaisse l'arrière de la liste.
    main_eps = pending[:main_n]
    laptop_eps = pending[main_n:]

    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)

    eps_map = {
        e["guid"]: {"youtubeUrl": e["youtubeUrl"], "title": e["title"]}
        for e in pending
    }
    # newline="\n" : on FORCE le LF Unix, sinon Python sur Windows écrit du
    # CRLF qui casse le `read` bash côté portable (CR parasite dans la variable).
    (DISPATCH_DIR / "episodes.json").write_text(
        json.dumps(eps_map, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n",
    )
    (DISPATCH_DIR / "main_guids.txt").write_text(
        "\n".join(e["guid"] for e in main_eps) + "\n",
        encoding="utf-8", newline="\n",
    )
    (DISPATCH_DIR / "laptop_guids.txt").write_text(
        "\n".join(e["guid"] for e in laptop_eps) + "\n",
        encoding="utf-8", newline="\n",
    )

    log.info("Pending: %d épisodes  →  main: %d   portable: %d",
             total, main_n, laptop_n)
    log.info("Écrit dans %s", DISPATCH_DIR)


if __name__ == "__main__":
    main()
