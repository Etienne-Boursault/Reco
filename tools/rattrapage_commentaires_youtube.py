"""
rattrapage_commentaires_youtube.py — poster les recos sous les ANCIENNES vidéos.

POURQUOI
--------
L'étape `commenter` de la chaîne ne commente que les épisodes sortis depuis
`RECO_YT_COMMENTAIRES_DEPUIS` (2026-10-22). Les 113 vidéos plus anciennes qui
ont des recos validées attendent leur commentaire. Décision d'Étienne du
2026-11-02 (YT-1) : un rattrapage lent, quatre vidéos par jour, pour que tout
soit prêt avant la V2 ; pas de ligne de playlist dans le message (YT-2 B).

COMMENT
-------
Chaque appel poste sous `--nombre` vidéos au plus (1 par défaut ; la cron de
venus passe quatre fois par jour), de la plus récente à la plus ancienne. Le
texte est celui de l'étape `commenter` (`commentaire_youtube.texte`) : mêmes
lignes, mêmes minutages, absents quand la reco vient de l'audio Acast.

L'état vit dans `tools/output/pipeline/rattrapage-commentaires-youtube.json`
(hors dépôt) : les vidéos commentées, et celles mises de côté sur un échec
propre à la vidéo (commentaires fermés, page de l'épisode sans ses recos). Une
vidéo mise de côté n'est pas retentée ; la retirer du fichier suffit pour
qu'elle revienne. Un échec du jeton OAuth, lui, ne met rien de côté : il arrête
le passage et se signale.

Matrix reçoit un récapitulatif par jour (`--recap`, au dernier passage), les
échecs et la fin du rattrapage — pas un message par vidéo, qui ferait quatre
messages par jour pendant un mois.

RELECTURE SANS COMPTE
---------------------
YouTube peut accepter un commentaire (l'API rend un identifiant) puis l'effacer
ou le masquer au public, tout de suite ou des heures plus tard ; l'API, lue avec
le jeton de la chaîne, continue alors de le voir (essais du 2026-11-02 : S6-E03
public à 20 h 15, masqué à 22 h). Chaque commentaire est donc relu SANS COMPTE
(yt-dlp) 40 s après son envoi, puis à chaque passage pendant deux jours. Au
premier commentaire introuvable, le rattrapage se suspend (`suspendu` dans
l'état) et le signale : continuer posterait des messages que personne ne voit,
et chargerait la chaîne aux yeux des filtres de YouTube. Retirer `suspendu` du
fichier le relance.

INERTE sans `RECO_YT_COMMENTAIRES=1` et les secrets OAuth (comme l'étape
`commenter`). Aperçu sans rien poster : `--apercu`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import commentaire_youtube as cy
import common

log = logging.getLogger("rattrapage_commentaires_youtube")

Notify = Callable[[str], None]
EstPublic = Callable[[str, str], bool]

#: Délai avant la première relecture d'un commentaire qui vient de partir.
DELAI_RELECTURE_S = 40
#: Durée pendant laquelle chaque passage relit un commentaire déjà posté.
RELIRE_PENDANT = timedelta(days=2)
#: Commentaires les plus récents lus sans compte pour retrouver le nôtre.
COMMENTAIRES_LUS = 300


def est_public(video: str, commentaire: str) -> bool:  # pragma: no cover — réseau réel
    """Le commentaire est-il visible SANS COMPTE sous la vidéo ?"""
    import yt_dlp
    options = {"quiet": True, "no_warnings": True, "skip_download": True, "getcomments": True,
               "extractor_args": {"youtube": {"comment_sort": ["new"],
                                              "max_comments": [str(COMMENTAIRES_LUS), "all", "0"]}}}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video}", download=False)
    return any(c.get("id") == commentaire for c in info.get("comments") or [])


def _masque(etat: dict[str, Any], guid: str, quand: str, notify: Notify) -> None:
    poste = etat["postes"][guid]
    poste["masque"] = quand
    etat["suspendu"] = f"commentaire de « {poste.get('titre', guid)} » invisible sans compte"
    notify(f"💬 Rattrapage YouTube suspendu : le commentaire posté sous « "
           f"{poste.get('titre', guid)} » n'est pas visible sans compte "
           f"(https://www.youtube.com/watch?v={poste['video']}&lc={poste['commentaire']}). "
           f"Retirer « suspendu » de l'état pour reprendre.")


def relire_recents(etat: dict[str, Any], notify: Notify, verifier: EstPublic,
                   maintenant: str) -> bool:
    """Relit sans compte les commentaires des deux derniers jours. Rend False,
    et suspend le rattrapage, dès que l'un d'eux a disparu."""
    limite = datetime.fromisoformat(maintenant) - RELIRE_PENDANT
    for guid, poste in etat["postes"].items():
        if poste.get("masque") or datetime.fromisoformat(poste["le"]) < limite:
            continue
        if not verifier(poste["video"], poste["commentaire"]):
            _masque(etat, guid, maintenant, notify)
            return False
    return True


def etat_path() -> Path:
    return common.OUTPUT_DIR / "pipeline" / "rattrapage-commentaires-youtube.json"


def charger_etat(chemin: Path) -> dict[str, Any]:
    if not chemin.exists():
        return {"postes": {}, "de_cote": {}}
    etat = json.loads(chemin.read_text(encoding="utf-8"))
    etat.setdefault("postes", {})
    etat.setdefault("de_cote", {})
    return etat


def sauver_etat(chemin: Path, etat: dict[str, Any]) -> None:
    common.write_json_if_changed(chemin, etat)


def video_id(url: str | None) -> str | None:
    """« https://www.youtube.com/watch?v=8jkQGlHZcs0 » → « 8jkQGlHZcs0 »."""
    if not url:
        return None
    parties = urlsplit(url)
    if parties.hostname == "youtu.be":
        return parties.path.strip("/") or None
    return (parse_qs(parties.query).get("v") or [None])[0]


def en_attente(source_id: str, etat: dict[str, Any],
               env: Mapping[str, str] = os.environ) -> list[tuple[dict[str, Any], str, list]]:
    """(épisode, vidéo, recos) des anciennes vidéos à commenter, la plus
    récente d'abord. Un épisode sans reco validée n'a rien à annoncer."""
    depuis = env.get("RECO_YT_COMMENTAIRES_DEPUIS") or cy.DEPUIS_PAR_DEFAUT
    faits = set(etat["postes"]) | set(etat["de_cote"])
    episodes = []
    for chemin in (common.EPISODES_DIR / source_id).glob("*.json"):
        ep = json.loads(chemin.read_text(encoding="utf-8"))
        video = video_id(ep.get("youtubeUrl"))
        # Les épisodes récents relèvent de l'étape `commenter` : ne jamais
        # poster deux fois sous la même vidéo.
        if not video or str(ep.get("date", "")) >= depuis or ep["guid"] in faits:
            continue
        episodes.append((ep, video))
    episodes.sort(key=lambda e: (str(e[0].get("date", "")), e[0]["guid"]), reverse=True)
    sortie = []
    for ep, video in episodes:
        recos = cy.recos_publiees(source_id, ep["guid"])
        if recos:
            sortie.append((ep, video, recos))
    return sortie


def rattraper(source_id: str, nombre: int, notify: Notify, *, chemin: Path,
              recap: bool = False,
              session: Any = None, env: Mapping[str, str] = os.environ,
              maintenant: Callable[[], str] = lambda: datetime.now().isoformat(timespec="seconds"),
              verifier: EstPublic = est_public,
              attendre: Callable[[float], None] = time.sleep,
              ) -> int:
    """Poste sous `nombre` vidéos au plus. Rend le nombre de commentaires
    postés et restés visibles."""
    if not cy.actif(env):
        log.info("étape inactive (RECO_YT_COMMENTAIRES ou secrets absents)")
        return 0
    if session is None:  # pragma: no cover — branche réseau réelle
        import requests
        session = requests.Session()
    etat = charger_etat(chemin)
    if etat.get("suspendu"):
        log.info("rattrapage suspendu : %s", etat["suspendu"])
        return 0
    if not relire_recents(etat, notify, verifier, maintenant()):
        sauver_etat(chemin, etat)
        return 0
    file = en_attente(source_id, etat, env)
    if not file:
        if not etat.get("termine"):
            etat["termine"] = maintenant()
            sauver_etat(chemin, etat)
            notify(f"💬 Rattrapage des commentaires YouTube terminé : "
                   f"{len(etat['postes'])} vidéo(s) commentée(s), "
                   f"{len(etat['de_cote'])} mise(s) de côté.")
        return 0
    site = env.get("SITE_URL") or cy.SITE_PAR_DEFAUT
    try:
        jeton = cy.jeton_d_acces(session, env)
    except Exception as exc:  # noqa: BLE001 — rien n'est mis de côté.
        notify(f"💬 Rattrapage des commentaires YouTube arrêté, jeton refusé : "
               f"{type(exc).__name__}: {str(exc)[:160]}")
        return 0
    postes = 0
    for ep, video, recos in file[:nombre]:
        guid, titre = ep["guid"], ep.get("title", ep["guid"])
        adresse = cy.adresse_episode(source_id, guid, site)
        if not cy.page_en_ligne(adresse, recos, session):
            raison = "la page de l'épisode ne montre pas toutes ses recos"
        else:
            try:
                ident = cy.poster(session, jeton, video, cy.texte(recos))
            except Exception as exc:  # noqa: BLE001 — propre à cette vidéo.
                raison = f"{type(exc).__name__}: {str(exc)[:160]}"
            else:
                etat["postes"][guid] = {"video": video, "commentaire": ident, "titre": titre,
                                        "le": maintenant(), "recos": len(recos)}
                log.info("%s : commentaire %s sous %s", titre, ident, video)
                sauver_etat(chemin, etat)
                attendre(DELAI_RELECTURE_S)
                if not verifier(video, ident):
                    _masque(etat, guid, maintenant(), notify)
                    sauver_etat(chemin, etat)
                    return postes
                postes += 1
                continue
        etat["de_cote"][guid] = {"video": video, "raison": raison, "le": maintenant()}
        sauver_etat(chemin, etat)
        notify(f"💬 Rattrapage YouTube : « {titre} » mis de côté ({raison}). "
               f"Le retirer de {chemin.name} pour le retenter.")
    if recap:
        _recapituler(source_id, etat, notify, maintenant()[:10], env)
    return postes


def _recapituler(source_id: str, etat: dict[str, Any], notify: Notify, jour: str,
                 env: Mapping[str, str]) -> None:
    """Un message pour les vidéos commentées ce jour-là ; rien si aucune."""
    du_jour = [v for v in etat["postes"].values()
               if str(v.get("le", "")).startswith(jour) and not v.get("masque")]
    if not du_jour:
        return
    reste = len(en_attente(source_id, etat, env))
    titres = " ; ".join(v.get("titre") or v["video"] for v in du_jour)
    notify(f"💬 Rattrapage YouTube du jour : {len(du_jour)} vidéo(s) commentée(s) "
           f"({titres}). Reste {reste} vidéo(s).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Poste les recos sous les anciennes vidéos YouTube, quelques-unes à la fois.")
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--nombre", type=int, default=1, help="vidéos au plus par appel")
    parser.add_argument("--apercu", action="store_true",
                        help="affiche les prochains messages sans rien poster")
    parser.add_argument("--notifier", choices=("matrix", "none"), default="none")
    parser.add_argument("--recap", action="store_true",
                        help="envoie le récapitulatif du jour (dernier passage de la journée)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    chemin = etat_path()
    if args.apercu:
        etat = charger_etat(chemin)
        file = en_attente(args.source, etat)
        print(f"{len(file)} vidéo(s) en attente.\n")
        for ep, video, recos in file[:args.nombre]:
            print(f"── {ep.get('title')} ({ep.get('date')}) https://www.youtube.com/watch?v={video}")
            print(cy.texte(recos) + "\n")
        return 0
    from traiter_nouveaux_episodes import build_notify
    rattraper(args.source, args.nombre, build_notify(args.notifier), chemin=chemin,
              recap=args.recap)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
