"""
match_youtube.py — Étape (optionnelle) du pipeline « Reco ».

Associe chaque épisode à sa vidéo YouTube, pour permettre des liens profonds
« vérifier au timecode » sur les cartes de reco.

Méthode : liste les vidéos de la chaîne (`youtubeChannel` de la source) via
yt-dlp en mode « flat » (rapide, sans téléchargement), puis matche chaque
épisode RSS à la vidéo dont le titre est le plus proche (similarité de chaînes
normalisées). Au-dessus d'un seuil de confiance, écrit `youtubeUrl` dans le JSON
de l'épisode.

Idempotent : un `youtubeUrl` déjà présent n'est pas écrasé (sauf --force).

Usage :
    python match_youtube.py --source un-bon-moment [--threshold 0.5] [--force] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from difflib import SequenceMatcher

from common import (
    list_episode_files,
    load_source,
    log,
    read_json,
    write_json_if_changed,
)

# Suffixe « (Un Bon Moment, S5-E31) » / « (A Good Time, …) » retiré avant match.
_SUFFIX_RE = re.compile(r"\((?:un bon moment|a good time)[^)]*\)", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Minuscule, sans accents, sans ponctuation, espaces normalisés."""
    text = _SUFFIX_RE.sub(" ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Mots vides ignorés pour la comparaison « par contenu ».
_STOPWORDS = {
    "un", "bon", "moment", "avec", "le", "la", "les", "et", "des", "de", "du",
    "a", "au", "aux", "en", "the", "good", "time", "l", "d",
}


def _content_tokens(s: str) -> set[str]:
    """Mots significatifs d'un titre (noms propres surtout)."""
    return {t for t in s.split() if t not in _STOPWORDS and len(t) > 1}


def _similarity(a: str, b: str) -> float:
    """Score de similarité combinant ratio de séquence, recouvrement et inclusion."""
    seq = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0
    base = 0.5 * seq + 0.5 * jaccard

    # Inclusion : si tous les mots significatifs du titre RSS (souvent juste le
    # prénom de l'invité) sont présents dans le titre YouTube → match fort.
    # Gère les titres courts « avec Waly » -> « Un Bon Moment avec WALY DIA ».
    ca = _content_tokens(a)
    if ca and ca <= _content_tokens(b):
        return max(base, 0.9)
    return base


def _fetch_channel_videos(channel_url: str) -> list[dict[str, str]]:
    """Liste (id, title) des vidéos de la chaîne via yt-dlp (flat, sans DL)."""
    import yt_dlp  # noqa: PLC0415 — import paresseux.

    videos_url = channel_url.rstrip("/")
    if not videos_url.endswith("/videos"):
        videos_url += "/videos"

    log.info("Listing des vidéos de la chaîne : %s", videos_url)
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(videos_url, download=False)

    entries = info.get("entries") or []
    videos = [
        {"id": e["id"], "title": e.get("title", ""), "duration": e.get("duration")}
        for e in entries
        if e and e.get("id")
    ]
    log.info("%d vidéo(s) trouvée(s) sur la chaîne.", len(videos))
    return videos


def _video_id(url: str) -> str | None:
    """Extrait l'identifiant d'une URL YouTube watch?v=…."""
    m = re.search(r"[?&]v=([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else None


def _parse_se(title: str) -> tuple[int | None, int | None]:
    """Extrait (saison, épisode) d'un titre type « (Un Bon Moment, S5-E31) »."""
    m = re.search(r"\bS(\d+)\s*[-–·.]?\s*E(\d+)\b", title or "", re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _apply_video_meta(episode: dict, video: dict) -> bool:
    """Recopie titre/durée/saison/numéro depuis la vidéo. Renvoie True si modifié."""
    changed = False
    title = video.get("title")
    if title and episode.get("youtubeTitle") != title:
        episode["youtubeTitle"] = title
        changed = True
    dur = video.get("duration")
    if dur and episode.get("youtubeDuration") != int(dur):
        episode["youtubeDuration"] = int(dur)
        changed = True
    season, number = _parse_se(title or "")
    if season and episode.get("season") != season:
        episode["season"] = season
        changed = True
    if number and episode.get("number") != number:
        episode["number"] = number
        changed = True
    return changed


def match_youtube(source_id: str, threshold: float, force: bool, dry_run: bool) -> int:
    """Associe les épisodes à leurs vidéos YouTube. Renvoie le nombre de liens posés."""
    source = load_source(source_id)
    channel = source.get("youtubeChannel")
    if not channel:
        raise ValueError(f"La source « {source_id} » n'a pas de youtubeChannel.")

    videos_all = _fetch_channel_videos(channel)
    if not videos_all:
        log.warning("Aucune vidéo récupérée — abandon.")
        return 0
    # Filtrer les extraits : règle métier — un épisode du podcast fait ≥ 30 min.
    # Les vidéos plus courtes sont des EXTRAITS, JEUX, BLINDTESTS, etc. — pas l'épisode source.
    # On les écarte du matching pour éviter qu'un titre RSS soit lié à un extrait.
    MIN_EPISODE_SECONDS = 30 * 60
    videos = [v for v in videos_all
              if v.get("duration") is None or v["duration"] >= MIN_EPISODE_SECONDS]
    n_excluded = len(videos_all) - len(videos)
    if n_excluded:
        log.info("Filtré %d extrait(s) < 30 min (gardé %d vidéo(s) candidates).",
                 n_excluded, len(videos))
    norm_videos = [(v, _normalize(v["title"])) for v in videos]
    # meta_by_id couvre TOUTES les vidéos pour qu'un lien manuel vers un extrait
    # garde quand même les métadonnées (titre/durée), même si on ne les propose plus.
    meta_by_id = {v["id"]: v for v in videos_all}

    written = 0
    for path in list_episode_files(source_id):
        episode = read_json(path)
        changed = False
        existing = episode.get("youtubeUrl")

        if existing and not force:
            # Déjà associé : on complète titre/durée/saison/numéro si possible.
            video = meta_by_id.get(_video_id(existing) or "")
            if video:
                changed = _apply_video_meta(episode, video)
        else:
            target = _normalize(episode.get("title", ""))
            best, best_score = None, 0.0
            for video, ntitle in norm_videos:
                score = _similarity(target, ntitle)
                if score > best_score:
                    best, best_score = video, score

            if target and best and best_score >= threshold:
                log.info("Match (%.2f) : « %s » -> « %s »", best_score,
                         episode.get("title", "?"), best["title"])
                if not dry_run:
                    episode["youtubeUrl"] = f"https://www.youtube.com/watch?v={best['id']}"
                    _apply_video_meta(episode, best)
                    changed = True
            else:
                log.info("Pas de correspondance fiable (%.2f) pour « %s ».",
                         best_score, episode.get("title", "?"))

        if changed and not dry_run and write_json_if_changed(path, episode):
            written += 1

    log.info("Terminé : %d épisode(s) mis à jour (liens/durées).", written)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Associe les épisodes à leurs vidéos YouTube (matching par titre)."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Seuil de confiance du match (0-1, défaut: 0.5).")
    parser.add_argument("--force", action="store_true",
                        help="Réécrit même si youtubeUrl existe déjà.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Affiche les correspondances sans rien écrire.")
    args = parser.parse_args()
    match_youtube(args.source, args.threshold, args.force, args.dry_run)


if __name__ == "__main__":
    main()
