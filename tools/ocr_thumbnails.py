"""
ocr_thumbnails.py — Complète le numéro d'épisode depuis la MINIATURE YouTube.

Les anciens épisodes (titre sans « SX-EX ») affichent « ÉPISODE NN » sur leur
miniature. Ce script télécharge la miniature des épisodes sans `number` mais
ayant une `youtubeUrl`, lit le numéro via l'API vision d'Anthropic (modèle
Haiku, peu coûteux), et l'écrit dans le JSON de l'épisode.

Usage :
    python ocr_thumbnails.py --source un-bon-moment [--dry-run]
"""

from __future__ import annotations

import argparse
import base64
import re

import requests

from common import list_episode_files, log, read_json, write_json_if_changed

MODEL = "claude-haiku-4-5"
_HEADERS = {"User-Agent": "Mozilla/5.0"}
_PROMPT = (
    "Cette miniature de podcast affiche-t-elle un numéro d'épisode "
    "(ex. « ÉPISODE 42 ») ? Réponds UNIQUEMENT par le nombre (ex. 42), "
    "ou par NONE s'il n'y a pas de numéro visible."
)


def _video_id(url: str) -> str | None:
    m = re.search(r"[?&]v=([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else None


def _download_thumb(video_id: str) -> bytes | None:
    """Télécharge la miniature (maxres, repli hq). Renvoie les octets JPEG."""
    for quality in ("maxresdefault", "hqdefault"):
        url = f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
        r = requests.get(url, headers=_HEADERS, timeout=30)
        if r.ok and len(r.content) > 2000:
            return r.content
    return None


def _read_number(client, image: bytes) -> int | None:
    """Demande au modèle vision le numéro d'épisode affiché sur la miniature."""
    b64 = base64.standard_b64encode(image).decode()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=20,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": _PROMPT},
            ],
        }],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def run(source_id: str, dry_run: bool) -> int:
    from common import make_anthropic_client  # noqa: PLC0415 — paresseux.

    client = None if dry_run else make_anthropic_client()
    written = 0
    for path in list_episode_files(source_id):
        episode = read_json(path)
        if episode.get("number") or not episode.get("youtubeUrl"):
            continue
        vid = _video_id(episode["youtubeUrl"])
        if not vid:
            continue
        image = _download_thumb(vid)
        if not image:
            log.warning("Miniature introuvable pour %s.", episode.get("title", "?"))
            continue
        if dry_run:
            log.info("[DRY-RUN] OCR de la miniature : %s", episode.get("title", "?"))
            continue
        number = _read_number(client, image)
        if number:
            episode["number"] = number
            if write_json_if_changed(path, episode):
                written += 1
                log.info("Épisode #%d : « %s »", number, episode.get("title", "?"))
        else:
            log.info("Pas de numéro lisible : « %s »", episode.get("title", "?"))
    log.info("Terminé : %d numéro(s) ajouté(s) depuis les miniatures.", written)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR du numéro d'épisode sur la miniature YouTube.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.source, args.dry_run)


if __name__ == "__main__":
    main()
