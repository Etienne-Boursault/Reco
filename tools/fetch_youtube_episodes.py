"""
fetch_youtube_episodes.py — crée les nouveaux épisodes depuis la chaîne YouTube.

YouTube est la source d'un épisode, pas Acast. Relevé sur les cinq derniers
épisodes de la saison 5 : la vidéo sort le dimanche à 08:00 UTC, le flux Acast
ne reçoit l'épisode que le lundi entre 03:00 et 04:00 UTC. `fetch_episodes.py`,
qui lit le flux, faisait attendre un jour pour rien — la transcription venait
déjà de YouTube.

Un épisode créé ici a pour identifiant `yt-<id de la vidéo>`. Le préfixe dit la
provenance, et évite qu'un id commençant par un tiret (`-lc9eAEFlUk`) soit pris
pour une option en ligne de commande. Les épisodes antérieurs gardent leur guid
Acast : il figure dans leurs URL publiques, déjà indexées.

Une vidéo est un épisode si son titre porte le suffixe du podcast
(`youtubeTitleSuffixPatterns`) ET une saison et un numéro (« S6-E1 »). Toute
autre vidéo NOUVELLE est rapportée, jamais traitée : un changement de format de
titre ne doit pas faire manquer un épisode en silence.

Garde-fous :
  - une vidéo déjà liée à un épisode (par id, ou par saison + numéro pour un
    épisode Acast sans `youtubeUrl`) n'est jamais recréée ;
  - une avant-première pas encore diffusée est remise au passage suivant ;
  - au premier passage, les vidéos non reconnues sont marquées vues sans être
    rapportées (sinon toute la chaîne le serait), mais un épisode reconnu est
    créé quand même : un service installé après la sortie le rattrape.

État : `tools/output/youtube/<source>.json`, les vidéos déjà vues.

Usage :
    python fetch_youtube_episodes.py --source un-bon-moment [--limit 15] [--dry-run] [--json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# isort: off — `common` d'abord : son import amorce `sys.path` pour `tools.`,
# dont dépend `match_youtube` (cf. l'en-tête de match_youtube.py).
import common
from common import (
    episodes_dir_for,
    extract_youtube_id,
    list_episode_files,
    load_source,
    log,
    read_json,
    slugify,
    write_json_if_changed,
)
from match_youtube import _build_suffix_regex, _parse_se

# isort: on

DEFAULT_LIMIT = 15
GUID_PREFIX = "yt-"
# Une vidéo en ligne depuis des mois n'a rien à faire dans l'état : on borne.
_MAX_SEEN = 500
_NOT_YET_AVAILABLE = frozenset({"is_upcoming", "is_live", "post_live"})
# Sans cette option, yt-dlp renvoie les titres TRADUITS AUTOMATIQUEMENT en
# anglais (« Orelsan is the final boss of the season ») : l'épisode porterait
# un titre anglais sur le site. D'où aussi « a good time » parmi les motifs de
# suffixe de la source : c'est « un bon moment » traduit.
_YTDLP_BASE = {"quiet": True, "no_warnings": True, "skip_download": True,
               "extractor_args": {"youtube": {"lang": ["fr"]}}}

Lister = Callable[[str, int], list[dict[str, Any]]]
Detailer = Callable[[str], dict[str, Any]]


@dataclass
class YoutubeFetchResult:
    first_run: bool = False
    created: list[str] = field(default_factory=list)
    unrecognized: list[dict[str, str]] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)


def list_channel_videos(channel_url: str, limit: int) -> list[dict[str, Any]]:
    """Les `limit` dernières vidéos de la chaîne (id, titre), les plus récentes d'abord."""
    import yt_dlp

    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"
    opts = {**_YTDLP_BASE, "extract_flat": True, "playlistend": limit}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return [{"id": e["id"], "title": e.get("title") or ""}
            for e in (info.get("entries") or []) if e and e.get("id")]


def video_details(video_id: str) -> dict[str, Any]:
    """Métadonnées complètes d'une vidéo (date, description, durée, statut)."""
    import yt_dlp

    with yt_dlp.YoutubeDL(_YTDLP_BASE) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    keys = ("id", "title", "description", "duration", "release_timestamp",
            "timestamp", "upload_date", "live_status")
    return {k: info.get(k) for k in keys}


def _publication_date(details: dict[str, Any]) -> str | None:
    stamp = details.get("release_timestamp") or details.get("timestamp")
    if stamp:
        return dt.datetime.fromtimestamp(int(stamp), dt.UTC).date().isoformat()
    day = str(details.get("upload_date") or "")
    if len(day) == 8 and day.isdigit():
        return f"{day[:4]}-{day[4:6]}-{day[6:]}"
    return None


def build_episode(source_id: str, details: dict[str, Any], season: int,
                  number: int) -> dict[str, Any]:
    """Épisode au schéma `episodes`, construit depuis la vidéo seule."""
    video_id = details["id"]
    title = (details.get("title") or "").strip()
    episode: dict[str, Any] = {
        "sourceId": source_id,
        "guid": GUID_PREFIX + video_id,
        "title": title,
        "youtubeTitle": title,
        "youtubeUrl": f"https://www.youtube.com/watch?v={video_id}",
        "season": season,
        "number": number,
        "guests": [],
        "transcriptStatus": "none",
    }
    date = _publication_date(details)
    if date:
        episode["date"] = date
    if details.get("duration"):
        episode["youtubeDuration"] = int(details["duration"])
    description = (details.get("description") or "").strip()
    if description:
        episode["description"] = description
    return episode


def state_path(source_id: str) -> Path:
    # Résolu à l'appel : les tests redirigent `common.OUTPUT_DIR`.
    return common.OUTPUT_DIR / "youtube" / f"{slugify(source_id)}.json"


def _load_seen(source_id: str) -> list[str] | None:
    path = state_path(source_id)
    if not path.exists():
        return None
    return [str(v) for v in read_json(path).get("seenVideoIds") or []]


def _save_seen(source_id: str, seen: list[str]) -> None:
    path = state_path(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    unique = list(dict.fromkeys(seen))[-_MAX_SEEN:]
    write_json_if_changed(path, {
        "seenVideoIds": unique,
        "lastCheckedAt": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
    })


def _known_episodes(source_id: str) -> tuple[set[str], set[tuple[int, int]]]:
    """Ids de vidéos déjà liées, et couples (saison, numéro) déjà présents."""
    video_ids: set[str] = set()
    numbers: set[tuple[int, int]] = set()
    for path in list_episode_files(source_id):
        episode = read_json(path)
        video_id = extract_youtube_id(episode.get("youtubeUrl"))
        if video_id:
            video_ids.add(video_id)
        if episode.get("season") and episode.get("number"):
            numbers.add((int(episode["season"]), int(episode["number"])))
    return video_ids, numbers


def fetch_youtube_episodes(source_id: str, *, limit: int = DEFAULT_LIMIT,
                           dry_run: bool = False,
                           lister: Lister | None = None,
                           detailer: Detailer | None = None) -> YoutubeFetchResult:
    # Résolus à l'appel et non dans la signature : un défaut figé à la
    # définition ne peut plus être remplacé, et la ligne de commande devient
    # intestable.
    lister = lister or list_channel_videos
    detailer = detailer or video_details
    source = load_source(source_id)
    channel = source.get("youtubeChannel")
    if not channel:
        raise ValueError(f"La source {source_id} n'a pas de youtubeChannel.")
    suffix_re = _build_suffix_regex(tuple(source.get("youtubeTitleSuffixPatterns") or ()))

    seen = _load_seen(source_id)
    result = YoutubeFetchResult(first_run=seen is None)
    already_seen = set(seen or ())
    known_ids, known_numbers = _known_episodes(source_id)
    newly_seen: list[str] = []

    for video in lister(channel, limit):
        video_id = video["id"]
        if video_id in already_seen or video_id in known_ids:
            continue
        title = video.get("title") or ""
        season, number = _parse_se(title)
        is_episode = bool(suffix_re and suffix_re.search(title) and season and number)
        if not is_episode:
            if not result.first_run:
                result.unrecognized.append({"id": video_id, "title": title})
            newly_seen.append(video_id)
            continue
        if (season, number) in known_numbers:
            log.info("S%s-E%s existe déjà (épisode Acast) : vidéo %s ignorée.",
                     season, number, video_id)
            newly_seen.append(video_id)
            continue
        try:
            details = detailer(video_id)
        except Exception as exc:  # noqa: BLE001 — une vidéo illisible attend le passage suivant.
            log.warning("Vidéo %s illisible pour l'instant : %s", video_id, exc)
            result.deferred.append(video_id)
            continue
        if details.get("live_status") in _NOT_YET_AVAILABLE:
            log.info("Vidéo %s pas encore diffusée (%s) : remise à plus tard.",
                     video_id, details.get("live_status"))
            result.deferred.append(video_id)
            continue
        episode = build_episode(source_id, details, season, number)
        if not dry_run:
            path = episodes_dir_for(source_id) / f"{slugify(episode['guid'])}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json_if_changed(path, episode)
        log.info("Épisode créé : %s — %s", episode["guid"], episode["title"])
        result.created.append(episode["guid"])
        newly_seen.append(video_id)

    if not dry_run:
        _save_seen(source_id, [*(seen or []), *newly_seen])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True, help="Identifiant de la source.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help="Nombre de vidéos récentes examinées (défaut: %(default)s).")
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien.")
    parser.add_argument("--json", action="store_true", help="Résultat en JSON sur stdout.")
    args = parser.parse_args(argv)
    result = fetch_youtube_episodes(args.source, limit=args.limit, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False))
    log.info("YouTube — créés : %d, non reconnues : %d, remises à plus tard : %d%s",
             len(result.created), len(result.unrecognized), len(result.deferred),
             " (premier passage)" if result.first_run else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
