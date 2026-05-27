"""
rematch_with_ocr.py — Re-match YouTube + validation OCR.

Pour chaque épisode visé (par défaut : ceux dont le lien YT actuel < 30 min,
donc un extrait), cherche la meilleure vidéo COMPLÈTE (≥ 30 min) sur la chaîne
en se basant sur la similarité de titre, puis VALIDE le match en lisant le
numéro affiché sur la miniature (OCR Haiku) et en le comparant au numéro
attendu de l'épisode. N'applique le nouveau lien que si OCR == numéro attendu.

Usage :
    python rematch_with_ocr.py --source un-bon-moment
        [--dry-run]            # n'écrit rien, juste journal
        [--guid GUID]          # cible 1 épisode précis (sinon : tous les extraits)
"""
from __future__ import annotations

import argparse
import base64
import json
import re
from difflib import SequenceMatcher

import requests

from common import (
    download_youtube_thumbnail,
    extract_youtube_id,
    list_episode_files,
    load_source,
    log,
    make_anthropic_client,
    read_json,
    write_json_if_changed,
)
from match_youtube import (
    _apply_video_meta,
    _fetch_channel_videos,
    _normalize,
)

MIN_FULL_EPISODE_SECONDS = 30 * 60
OCR_MODEL = "claude-haiku-4-5"
_OCR_PROMPT = (
    "Cette miniature de podcast YouTube affiche-t-elle un numéro d'épisode "
    "(ex. « ÉPISODE 42 », « EP 42 », « #42 ») ? Réponds UNIQUEMENT par le nombre "
    "(ex. 42), ou par NONE s'il n'y a pas de numéro visible."
)


def _ocr_episode_number(client, video_id: str) -> int | None:
    """OCR de la miniature → numéro d'épisode (ou None si non lisible)."""
    image = download_youtube_thumbnail(video_id)
    if not image:
        return None
    b64 = base64.standard_b64encode(image).decode()
    msg = client.messages.create(
        model=OCR_MODEL,
        max_tokens=20,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg", "data": b64,
                }},
                {"type": "text", "text": _OCR_PROMPT},
            ],
        }],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def _candidates(episode: dict, videos: list[dict], used_ids: set[str], top_n: int = 5):
    """Top-N candidats parmi les vidéos ≥ 30 min, triés par similarité de titre."""
    target = _normalize(episode.get("title", ""))
    if not target:
        return []
    scored = []
    for v in videos:
        if v["id"] in used_ids:
            continue
        if (v.get("duration") or 0) < MIN_FULL_EPISODE_SECONDS:
            continue
        score = SequenceMatcher(None, target, _normalize(v["title"])).ratio()
        scored.append((score, v))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_n]


def _episode_is_extract(d: dict) -> bool:
    yt_dur = d.get("youtubeDuration") or 0
    aud_dur = d.get("audioDuration") or 0
    return 0 < yt_dur < MIN_FULL_EPISODE_SECONDS and aud_dur >= MIN_FULL_EPISODE_SECONDS


def rematch(source_id: str, only_guid: str | None, dry_run: bool) -> None:
    # 1) Charger tous les épisodes + vidéos chaîne.
    ep_paths = list(list_episode_files(source_id))
    episodes = [(p, read_json(p)) for p in ep_paths]
    # load_source utilise common.SOURCES_DIR (absolu) — évite les bugs liés
    # au répertoire courant quand le script est lancé via SSH ou wrapper.
    src_cfg = load_source(source_id)
    channel = src_cfg["youtubeChannel"]
    videos = _fetch_channel_videos(channel)
    used_ids = {extract_youtube_id(d.get("youtubeUrl") or "") for _, d in episodes
                if d.get("youtubeUrl")}
    used_ids.discard(None)

    # 2) Cibler les épisodes-extraits (ou guid précis).
    targets = []
    for p, d in episodes:
        if only_guid:
            if d.get("guid") == only_guid:
                targets.append((p, d))
        elif _episode_is_extract(d):
            targets.append((p, d))

    log.info("Cibles : %d épisode(s) avec lien YT vers extrait.", len(targets))
    if not targets:
        return

    client = None if dry_run else make_anthropic_client()

    for p, ep in targets:
        expected = ep.get("number")
        log.info("\n=== %s (attend #%s) ===", ep.get("title", "?")[:55], expected)
        # Important : libérer l'id actuel pour qu'il ne soit pas dans used_ids.
        current_id = extract_youtube_id(ep.get("youtubeUrl") or "")
        candidates = _candidates(ep, videos, used_ids - {current_id})
        if not candidates:
            log.warning("  Aucun candidat ≥ 30 min — on garde le lien actuel.")
            continue

        chosen = None
        for score, v in candidates:
            log.info("  candidat sim=%.2f | %s", score, v["title"][:60])
            if dry_run:
                continue
            ocr_num = _ocr_episode_number(client, v["id"])
            log.info("    OCR miniature : %s (attendu : %s)", ocr_num, expected)
            if ocr_num is not None and expected is not None and ocr_num == expected:
                chosen = v
                break
        if not chosen:
            if not dry_run:
                log.warning("  ⚠️ Aucun candidat validé par OCR — on garde le lien actuel.")
            continue

        # Appliquer le nouveau match.
        new_url = f"https://www.youtube.com/watch?v={chosen['id']}"
        ep["youtubeUrl"] = new_url
        _apply_video_meta(ep, chosen)
        if expected is not None:
            ep["number"] = expected  # _apply_video_meta peut le ré-extraire du titre
        used_ids.discard(current_id)
        used_ids.add(chosen["id"])
        if write_json_if_changed(p, ep):
            log.info("  ✅ Match validé OCR. Lien YT remplacé : %s", chosen["title"][:55])


def main():
    parser = argparse.ArgumentParser(description="Re-match YouTube avec validation OCR.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--guid", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rematch(args.source, args.guid, args.dry_run)


if __name__ == "__main__":
    main()
