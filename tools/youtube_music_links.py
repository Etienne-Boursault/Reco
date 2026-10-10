"""YouTube Music des morceaux et des artistes, et l'Instagram que l'artiste publie.

La passe musicale sert Deezer, Apple Music, Spotify et Qobuz, pas YouTube
Music : sur S6-E04, les deux liens « YT Music » et l'Instagram de Carla de
Coignac ont été posés à la main. Aucune API sans clé ne sert YouTube Music ;
yt-dlp (déjà dans `requirements.txt` et dans l'image de venus) en tient lieu,
par la recherche « titres » de YouTube Music, qui ne rend que des pistes.

LA PREUVE : « PROVIDED TO YOUTUBE »
-----------------------------------
Les pistes que les distributeurs déposent sur YouTube ont une description
normalisée : « Provided to YouTube by IDOL », puis « Titre · Artiste ·
Artiste ». C'est une déclaration du distributeur, pas une ressemblance de
titre — et yt-dlp en tire `track`, `artists` et la chaîne qui la publie.
- **Morceau** : une piste « Provided to YouTube » dont le titre (sans sa
  parenthèse) ET l'un des artistes correspondent à la reco. « Sauf si c'est toi
  (Adaptation de Until i found you) » est la reco « Sauf si c'est toi (reprise
  française de Until I Found You) » : seule la parenthèse diffère, et deux
  artistes la corroborent.
- **Artiste** : la chaîne « Topic » sous laquelle YouTube range les pistes
  dont il est l'artiste PRINCIPAL. Plusieurs chaînes pour un même nom, c'est un
  homonyme ou une donnée bancale (Al'Tarba, mesuré) : refus `ambiguous`. Puis
  sa page YouTube Music doit avoir ce nom pour titre (une chaîne inconnue y
  répond « undefined »). Calibré le 2026-10-10 : Pomme, Booba, Spider ZED et
  Barbara retrouvent la chaîne que le corpus porte déjà.

L'INSTAGRAM
-----------
Une chaîne « Topic » ne publie aucun lien. Sa page nomme pourtant l'artiste
avec un lien vers sa chaîne OFFICIELLE (Carla de Coignac → UCQPGGM6…) ; c'est
la page « À propos » de celle-ci qui liste l'Instagram, retenu seulement s'il
est le SEUL compte cité. Il ne remplace jamais celui de Wikidata : la passe
tourne après `liens_wikidata`, et un hôte déjà présent n'est pas reposé.

⚠️ `lang=fr` est OBLIGATOIRE : sans lui, yt-dlp rend des titres traduits
automatiquement en anglais, et l'égalité de titre échoue.
"""
from __future__ import annotations

import argparse
import html
import re
import urllib.parse
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

import requests

import common
from common import log, normalize_text, parse_ids_option
from music_links_matching import artist_matches_collaborator, artist_matches_creator
from passe_liens import derouler
from streaming_links import PageInjoignable, _page
from wikidata_links import RapportWikidata, format_rapport
from wikidata_matching import (
    RAISON_AMBIGUOUS,
    RAISON_HTTP_ERROR,
    RAISON_NO_ENTITY,
    RAISON_NO_NEW_LINK,
    RAISON_OK,
    Lien,
    Resolution,
    hote,
)

TYPE_MORCEAU = "musique"
TYPE_ARTISTE = "artiste"
#: Pistes ouvertes au plus par reco : chaque ouverture coûte deux à trois secondes.
MAX_PISTES = 3
RECHERCHE = 5
PREFIXE_PISTE = "Provided to YouTube by"
PREUVE = "provided-to-youtube"
RAISON_NO_CREATOR = "no-creator-to-verify"
RAISON_TITRE_YT_MUSIC = "yt-music-title-mismatch"
PAUSE = 0.5

YT_MUSIC = ("ytmusic", "streaming", "neutral", "YT Music")
INSTAGRAM = ("instagram", "social", "neutral", "Instagram")
#: Ce qui suit `instagram.com/` sans être un compte.
_INSTAGRAM_GENERIQUES = frozenset({"youtube", "p", "reel", "explore", "accounts", "stories"})
_RE_INSTAGRAM = re.compile(r"instagram\.com(?:%2F|/)([A-Za-z0-9_.]+)")
_RE_TITRE_PAGE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_RE_PARENTHESE = re.compile(r"\s*[(\[][^)\]]*[)\]]\s*")
#: Un nom d'artiste cliquable dans la page d'une chaîne : le texte, la longueur
#: du lien depuis le début du texte, et la chaîne visée.
_RE_NOM_LIE = re.compile(
    r'"content":"([^"]+)","commandRuns":\[\{"startIndex":0,"length":(\d+),'
    r'"onTap":\{"innertubeCommand":\{"clickTrackingParams":"[^"]*",'
    r'"commandMetadata":\{"webCommandMetadata":\{"url":"/channel/(UC[\w-]{22})"')
_YTDLP_BASE = {"quiet": True, "no_warnings": True, "skip_download": True,
               "extractor_args": {"youtube": {"lang": ["fr"]}}}

Chercher = Callable[[str, int], list[dict[str, Any]]]
Detailler = Callable[[str], dict[str, Any]]


# ===== yt-dlp ===============================================================
def chercher(requete: str, nombre: int) -> list[dict[str, Any]]:
    """Pistes rendues par la recherche « titres » de YouTube Music (à plat)."""
    import yt_dlp

    url = f"https://music.youtube.com/search?q={urllib.parse.quote(requete)}#songs"
    with yt_dlp.YoutubeDL({**_YTDLP_BASE, "extract_flat": True,
                           "playlistend": nombre}) as ydl:
        info = ydl.extract_info(url, download=False)
    return [e for e in (info.get("entries") or []) if e][:nombre]


def detailler(video_id: str) -> dict[str, Any]:
    """Description, piste, artistes et chaîne d'une vidéo."""
    import yt_dlp

    with yt_dlp.YoutubeDL(_YTDLP_BASE) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    return {k: info.get(k)
            for k in ("id", "title", "description", "track", "artists", "channel_id")}


def _details(detailleur: Detailler, video_id: str) -> dict[str, Any]:
    """Une vidéo retirée ne doit pas faire échouer la reco : on passe à la suivante."""
    try:
        return detailleur(video_id)
    except Exception as exc:  # noqa: BLE001 — yt-dlp lève ses propres erreurs (DownloadError…).
        log.info("  vidéo %s illisible (%s) — ignorée", video_id, str(exc)[:80])
        return {}


# ===== couche pure ==========================================================
def sans_parenthese(titre: str | None) -> str:
    return normalize_text(_RE_PARENTHESE.sub(" ", titre or ""))


def est_une_piste(details: dict[str, Any]) -> bool:
    return str(details.get("description") or "").startswith(PREFIXE_PISTE)


def piste_officielle(details: dict[str, Any], titre: str, createur: str) -> bool:
    """La vidéo est-elle la piste « Provided to YouTube » de CE morceau ?"""
    piste = sans_parenthese(details.get("track") or details.get("title"))
    if not est_une_piste(details) or not piste or piste != sans_parenthese(titre):
        return False
    return any(artist_matches_creator(a, createur) or artist_matches_collaborator(a, createur)
               for a in details.get("artists") or [])


def chaine_de_lartiste(details: dict[str, Any], artiste: str) -> str | None:
    """Chaîne d'une piste dont `artiste` est l'artiste PRINCIPAL, sinon None.

    Le premier crédité seulement : un duo est rangé chez son premier artiste
    (« Laissez-moi danser » de Waxx et Pomme est chez Waxx, mesuré).
    """
    artistes = details.get("artists") or []
    canal = str(details.get("channel_id") or "")
    if (est_une_piste(details) and artistes and canal.startswith("UC")
            and normalize_text(artistes[0]) == normalize_text(artiste)):
        return canal
    return None


def chaine_officielle(page: str, artiste: str) -> str | None:
    """La chaîne vers laquelle la page lie le NOM de l'artiste, si elle est unique."""
    voulu = normalize_text(artiste)
    chaines = {canal for texte, longueur, canal in _RE_NOM_LIE.findall(page)
               if normalize_text(texte[:int(longueur)]) == voulu}
    return chaines.pop() if len(chaines) == 1 else None


def titre_de_page(page: str) -> str:
    m = _RE_TITRE_PAGE.search(page)
    return html.unescape(m.group(1)).strip() if m else ""


def instagram_unique(page: str) -> str | None:
    """Le seul compte Instagram listé par la page, ou None (aucun, ou plusieurs)."""
    comptes = {c.rstrip(".").lower() for c in _RE_INSTAGRAM.findall(page)}
    comptes -= _INSTAGRAM_GENERIQUES
    return f"https://www.instagram.com/{comptes.pop()}/" if len(comptes) == 1 else None


def servie(reco: dict[str, Any]) -> bool:
    return bool({TYPE_MORCEAU, TYPE_ARTISTE} & set(reco.get("types") or []))


def est_un_morceau(reco: dict[str, Any]) -> bool:
    """Morceau ou artiste ? Le corpus type souvent un artiste `artiste` +
    `musique`, avec lui-même pour créateur (« Booba » par Booba, relevé sur 7 des
    16 recos de calibrage) : c'est alors l'artiste, pas un titre."""
    types = reco.get("types") or []
    if TYPE_MORCEAU not in types:
        return False
    createur = normalize_text(reco.get("creator"))
    return TYPE_ARTISTE not in types or bool(createur and createur != normalize_text(
        reco.get("title")))


def _hotes(reco: dict[str, Any]) -> set[str]:
    return {hote(str(e.get("url") or "")) for e in reco.get("links") or []}


def _lien(source: tuple[str, str, str, str], url: str) -> Lien:
    return Lien(*source, url)


# ===== résolution ===========================================================
def resoudre_morceau(reco: dict[str, Any], *, chercheur: Chercher,
                     detailleur: Detailler) -> Resolution:
    titre, createur = str(reco.get("title") or ""), str(reco.get("creator") or "")
    if not createur.strip():
        return Resolution((), RAISON_NO_CREATOR)
    if "music.youtube.com" in _hotes(reco):
        return Resolution((), RAISON_NO_NEW_LINK)
    requete = f"{_RE_PARENTHESE.sub(' ', titre).strip()} {createur}"
    candidates = [str(e["id"]) for e in chercheur(requete, RECHERCHE)
                  if e.get("id") and sans_parenthese(e.get("title")) == sans_parenthese(titre)]
    for video_id in candidates[:MAX_PISTES]:
        if piste_officielle(_details(detailleur, video_id), titre, createur):
            # La première piste prouvée suffit : un single et son album sont
            # deux enregistrements officiels du même morceau, l'un vaut l'autre.
            url = f"https://music.youtube.com/watch?v={video_id}"
            return Resolution((_lien(YT_MUSIC, url),), RAISON_OK, PREUVE)
    return Resolution((), RAISON_NO_ENTITY, detail=f"{len(candidates)} candidate(s)")


def resoudre_artiste(reco: dict[str, Any], *, session: requests.Session,
                     chercheur: Chercher, detailleur: Detailler) -> Resolution:
    artiste = str(reco.get("title") or "")
    deja = _hotes(reco)
    if {"music.youtube.com", "instagram.com"} <= deja:
        return Resolution((), RAISON_NO_NEW_LINK)
    pistes = [str(e["id"]) for e in chercheur(artiste, RECHERCHE) if e.get("id")]
    chaines = {c for v in pistes[:MAX_PISTES]
               if (c := chaine_de_lartiste(_details(detailleur, v), artiste))}
    if not chaines:
        return Resolution((), RAISON_NO_ENTITY, detail=f"{len(pistes)} piste(s) lue(s)")
    if len(chaines) > 1:
        return Resolution((), RAISON_AMBIGUOUS, detail=" ".join(sorted(chaines)))
    topic = chaines.pop()
    titre = titre_de_page(_page(session, f"https://music.youtube.com/channel/{topic}").text)
    if normalize_text(titre) != normalize_text(artiste):
        return Resolution((), RAISON_TITRE_YT_MUSIC, detail=f"{topic} : {titre!r}")
    liens = []
    if "music.youtube.com" not in deja:
        liens.append(_lien(YT_MUSIC, f"https://music.youtube.com/channel/{topic}"))
    if "instagram.com" not in deja:
        officielle = chaine_officielle(
            _page(session, f"https://www.youtube.com/channel/{topic}").text, artiste)
        if officielle:
            apropos = _page(session, f"https://www.youtube.com/channel/{officielle}/about")
            if compte := instagram_unique(apropos.text):
                liens.append(_lien(INSTAGRAM, compte))
    if not liens:
        return Resolution((), RAISON_NO_NEW_LINK, PREUVE, topic)
    return Resolution(tuple(liens), RAISON_OK, PREUVE, topic)


def resoudre(reco: dict[str, Any], *, session: requests.Session,
             chercheur: Chercher | None = None,
             detailleur: Detailler | None = None) -> Resolution:
    """Morceau ou artiste ; une panne (recherche ou page) devient une raison, pas un arrêt.

    Clients résolus à l'appel : un défaut figé dans la signature serait lié à
    la définition, et un test qui remplace `chercher` partirait sur YouTube.
    """
    chercheur = chercheur or chercher
    detailleur = detailleur or detailler
    try:
        if est_un_morceau(reco):
            return resoudre_morceau(reco, chercheur=chercheur, detailleur=detailleur)
        return resoudre_artiste(reco, session=session, chercheur=chercheur,
                                detailleur=detailleur)
    except PageInjoignable as exc:
        return Resolution((), RAISON_HTTP_ERROR, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — la recherche yt-dlp lève ses propres erreurs.
        return Resolution((), RAISON_HTTP_ERROR, detail=f"yt-dlp : {str(exc)[:120]}")


def run(*, root: Path, session: requests.Session | None = None,
        source: str | None = None, ids: Iterable[str] = (),
        apply: bool = False, sleep: float = PAUSE) -> RapportWikidata:
    session = session or requests.Session()
    # Sans ce cookie, YouTube sert la page de consentement européenne.
    session.cookies.set("SOCS", "CAI", domain=".youtube.com")
    return derouler(root=root, source=source, ids=ids, servie=servie,
                    resoudre=lambda reco: resoudre(reco, session=session),
                    apply=apply, sleep=sleep)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="YT Music des morceaux et artistes, et l'Instagram de l'artiste.")
    parser.add_argument("--source")
    parser.add_argument("--root", type=Path, help="dossier des recos (défaut : le corpus)")
    parser.add_argument("--ids", help="ids de recos séparés par des virgules")
    parser.add_argument("--apply", action="store_true", help="écrire (défaut : simulation)")
    args = parser.parse_args(argv)
    rapport = run(root=args.root or common.RECOS_DIR, source=args.source,
                  ids=parse_ids_option(args.ids), apply=args.apply)
    log.info("%s", format_rapport(rapport))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
