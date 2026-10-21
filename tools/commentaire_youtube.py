"""
commentaire_youtube.py — poster les recos sous la video d'un nouvel episode.

CE QUE FAIT CETTE ETAPE
-----------------------
Une fois l'episode publie sur le site, la chaine poste sous sa video YouTube
un commentaire de la chaine « Une Bonne Reco » : chaque reco avec son minutage
(cliquable sur YouTube), puis le lien vers la page de l'episode.

QUAND
-----
Apres la publication (`state["published"]`), et seulement quand la page de
l'episode est EN LIGNE avec ses recos : poster un lien vers une page encore
absente — la PR n'est pas fusionnee, ou le deploiement tourne — enverrait les
lecteurs sur une 404. Tant que la page manque, l'etape repasse au tick suivant.

Seuls les episodes sortis depuis `RECO_YT_COMMENTAIRES_DEPUIS` (par defaut le
2026-10-22) sont commentes : les anciens ne recoivent rien d'un coup.

INERTE PAR DEFAUT
-----------------
Rien ne part sans `RECO_YT_COMMENTAIRES=1` et les trois secrets OAuth du
compte (`RECO_YT_CLIENT_ID`, `RECO_YT_CLIENT_SECRET`, `RECO_YT_REFRESH_TOKEN`)
dans le `.env` de venus. Le jeton s'obtient une fois avec
`tools/youtube_autoriser.py`. Un apercu sans rien poster :
`python commentaire_youtube.py --apercu <guid>`.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

log = logging.getLogger("commentaire_youtube")

SITE_PAR_DEFAUT = "https://unebonnere.co"
JETON_URL = "https://oauth2.googleapis.com/token"
COMMENTAIRE_URL = "https://www.googleapis.com/youtube/v3/commentThreads?part=snippet"
#: YouTube refuse au-dela de 10 000 caracteres.
LONGUEUR_MAX = 10_000
SECRETS = ("RECO_YT_CLIENT_ID", "RECO_YT_CLIENT_SECRET", "RECO_YT_REFRESH_TOKEN")
#: Episodes sortis avant l'arrivee de l'etape : jamais commentes.
DEPUIS_PAR_DEFAUT = "2026-10-22"

Notify = Callable[[str], None]


def actif(env: Mapping[str, str] = os.environ) -> bool:
    return env.get("RECO_YT_COMMENTAIRES") == "1" and all(env.get(s) for s in SECRETS)


def minutage(horodatage: str | None) -> str | None:
    """« 00:01:10 » -> « 1:10 », « 01:23:58 » -> « 1:23:58 » (forme que
    YouTube rend cliquable). `None` si l'horodatage est illisible."""
    try:
        h, m, s = (int(x) for x in (horodatage or "").split(":"))
    except ValueError:
        return None
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def recos_publiees(source_id: str, guid: str) -> list[dict[str, Any]]:
    """Les recos validees de l'episode, evocations comprises, dans l'ordre
    de l'episode."""
    recos = []
    for chemin in (common.RECOS_DIR / source_id).glob("*.json"):
        doc = json.loads(chemin.read_text(encoding="utf-8"))
        if doc.get("episodeGuid") == guid and doc.get("status") == "validated":
            recos.append(doc)
    return sorted(recos, key=lambda r: r.get("timestamp") or "99:99:99")


def _ligne(r: dict[str, Any]) -> str:
    titre = r["title"]
    createur = r.get("creator")
    if createur and createur.casefold() != titre.casefold():
        titre = f"{titre} ({createur})"
    # Un minutage releve sur l'audio Acast ne correspond pas a la video :
    # mieux vaut aucun minutage qu'un minutage faux.
    quand = minutage(r.get("timestamp")) if r.get("transcriptSource") == "youtube" else None
    return f"{quand} {titre}" if quand else f"• {titre}"


def adresse_episode(source_id: str, guid: str, site: str) -> str:
    return f"{site.rstrip('/')}/{source_id}/episode/{guid}/"


def texte(recos: list[dict[str, Any]], adresse: str) -> str:
    """Les recommandations d'abord ; les simples evocations a part, comme sur
    le site, pour ne pas les faire passer pour des conseils."""
    conseils = [_ligne(r) for r in recos if r.get("kind") != "citation"]
    evocations = [_ligne(r) for r in recos if r.get("kind") == "citation"]
    parties = []
    if conseils:
        parties.append("Les recos de l'épisode :\n\n" + "\n".join(conseils))
    if evocations:
        parties.append("Aussi évoqués :\n\n" + "\n".join(evocations))
    message = (
        "\n\n".join(parties) + "\n\n"
        f"Tous les liens pour les écouter, les voir ou les lire : {adresse}\n\n"
        "Une Bonne Reco, le site de fan (non officiel) qui garde toutes les "
        "recos d'Un Bon Moment depuis le début."
    )
    return message[:LONGUEUR_MAX]


def page_en_ligne(adresse: str, recos: list[dict[str, Any]], session: Any) -> bool:
    """La page existe ET porte les recos : un 200 seul ne prouve pas que le
    deploiement contenant l'episode est passe."""
    try:
        reponse = session.get(adresse, timeout=30)
    except Exception as exc:  # noqa: BLE001 — reseau : on repassera.
        log.info("page %s injoignable : %s", adresse, exc)
        return False
    if reponse.status_code != 200:
        return False
    page = html.unescape(reponse.text)
    return all(r["title"] in page for r in recos)


def jeton_d_acces(session: Any, env: Mapping[str, str]) -> str:
    reponse = session.post(JETON_URL, timeout=30, data={
        "client_id": env["RECO_YT_CLIENT_ID"],
        "client_secret": env["RECO_YT_CLIENT_SECRET"],
        "refresh_token": env["RECO_YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    })
    reponse.raise_for_status()
    return reponse.json()["access_token"]


def poster(session: Any, jeton: str, video_id: str, message: str) -> str:
    """Poste le commentaire. Rend son identifiant."""
    reponse = session.post(
        COMMENTAIRE_URL, timeout=30,
        headers={"Authorization": f"Bearer {jeton}"},
        json={"snippet": {"videoId": video_id,
                          "topLevelComment": {"snippet": {"textOriginal": message}}}},
    )
    reponse.raise_for_status()
    return reponse.json()["id"]


def a_commenter(source_id: str, state: dict[str, Any], episodes: list,
                env: Mapping[str, str] = os.environ) -> list:
    """Episodes publies, revenus dans le depot (PR fusionnee), sortis depuis
    `RECO_YT_COMMENTAIRES_DEPUIS` et pas encore commentes. Vide tant que
    l'etape n'est pas activee.

    Une date plutot qu'une liste amorcee au premier passage : la sonde
    `a-commenter` ne sauvegarde pas l'etat, et un amorcage perdu aurait range
    le premier vrai episode parmi les anciens.
    """
    if not actif(env):
        return []
    depuis = env.get("RECO_YT_COMMENTAIRES_DEPUIS") or DEPUIS_PAR_DEFAUT
    deja = set(state.setdefault("commented", []))
    return [(chemin, ep) for chemin, ep in episodes
            if ep["guid"] in state.get("published", [])
            and str(ep.get("date", "")) >= depuis
            and ep["guid"] not in deja]


def commenter(source_id: str, notify: Notify, state: dict[str, Any], episodes: list, *,
              rapporter: Callable[..., None], oublier: Callable[..., None],
              session: Any = None, env: Mapping[str, str] = os.environ) -> int:
    if session is None:  # pragma: no cover — branche reseau reelle
        import requests
        session = requests.Session()
    site = env.get("SITE_URL") or SITE_PAR_DEFAUT
    for _, episode in a_commenter(source_id, state, episodes, env):
        guid = episode["guid"]
        recos = recos_publiees(source_id, guid)
        if not recos:
            # Rien a annoncer : on ne poste pas un commentaire vide.
            state["commented"].append(guid)
            continue
        adresse = adresse_episode(source_id, guid, site)
        if not page_en_ligne(adresse, recos, session):
            log.info("%s : page pas encore en ligne, on repassera", guid)
            continue
        cle = f"commentaire:{guid}"
        try:
            jeton = jeton_d_acces(session, env)
            identifiant = poster(session, jeton, guid.removeprefix("yt-"), texte(recos, adresse))
        except Exception as exc:  # noqa: BLE001 — signale une fois, retente ensuite.
            rapporter(state, cle, f"💬 Commentaire YouTube impossible pour « "
                      f"{episode.get('title', guid)} » : {type(exc).__name__}: "
                      f"{str(exc)[:160]}", notify)
            continue
        oublier(state, cle)
        state["commented"].append(guid)
        lien = f"https://www.youtube.com/watch?v={guid.removeprefix('yt-')}&lc={identifiant}"
        notify(f"💬 Recos postées sous la vidéo de « {episode.get('title', guid)} » "
               f"({len(recos)} reco(s)) : {lien}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apercu du commentaire YouTube d'un episode.")
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--apercu", metavar="GUID", required=True)
    args = parser.parse_args(argv)
    recos = recos_publiees(args.source, args.apercu)
    site = os.environ.get("SITE_URL") or SITE_PAR_DEFAUT
    print(texte(recos, adresse_episode(args.source, args.apercu, site)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
