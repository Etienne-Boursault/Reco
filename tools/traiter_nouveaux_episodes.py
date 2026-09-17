"""
traiter_nouveaux_episodes.py — la chaîne automatique d'un nouvel épisode.

Lancé à intervalles réguliers sur venus, en quatre temps que le script d'hôte
enchaîne (cf. deploy/venus/) :

    detecter    nouvelles vidéos de la chaîne -> épisodes `yt-…`
    transcrire  épisodes `yt-…` pas encore transcrits (faster-whisper, CPU)
    a-extraire  code 0 s'il reste un épisode transcrit à extraire, 1 sinon
    extraire    extraction des recos, puis message avec le lien de validation

Pourquoi découper : l'extraction prend le verrou pipeline, que le review_server
tient tant qu'il tourne (cf. review_lock.py). Le script d'hôte n'arrête donc la
page de validation que le temps d'`extraire` — une à deux minutes — et
seulement quand `a-extraire` a répondu qu'il y a du travail.

Seuls les épisodes `yt-…` sont concernés. Les épisodes Acast ont été traités à
la main : les ré-extraire serait facturé et écraserait des mois de relecture.

État : `tools/output/pipeline/<source>.json` — épisodes déjà extraits, et
dernière erreur signalée par étape et par épisode, pour qu'une panne qui dure
ne produise pas un message à chaque passage.

Usage :
    python traiter_nouveaux_episodes.py --source un-bon-moment detecter
    python traiter_nouveaux_episodes.py --source un-bon-moment transcrire
    python traiter_nouveaux_episodes.py --source un-bon-moment a-extraire
    python traiter_nouveaux_episodes.py --source un-bon-moment extraire
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import urllib.parse
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import common
from common import (
    list_episode_files,
    load_source,
    log,
    read_json,
    slugify,
    transcript_path_for,
    write_json_if_changed,
)
from fetch_youtube_episodes import GUID_PREFIX, fetch_youtube_episodes

# Mesuré sur le CPU de venus le 2026-09-17 : 4,8 × le temps réel, un épisode de
# 82 min en ~17 min. `large-v3` y tient 1,4 × : une heure par épisode.
WHISPER_MODEL = "large-v3-turbo"
DEFAULT_REVIEW_URL = "http://10.8.0.1:8000"

Notify = Callable[[str], None]


# ===== état ==================================================================
def state_path(source_id: str) -> Path:
    return common.OUTPUT_DIR / "pipeline" / f"{slugify(source_id)}.json"


def load_state(source_id: str) -> dict[str, Any]:
    path = state_path(source_id)
    state = read_json(path) if path.exists() else {}
    state.setdefault("extracted", [])
    state.setdefault("lastErrors", {})
    return state


def save_state(source_id: str, state: dict[str, Any]) -> None:
    path = state_path(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_if_changed(path, state)


def _report_once(state: dict[str, Any], key: str, message: str, notify: Notify) -> None:
    """Signale une erreur, sauf si c'est la même qu'au passage précédent."""
    log.error("%s", message)
    if state["lastErrors"].get(key) != message:
        notify(message)
        state["lastErrors"][key] = message


def _clear_error(state: dict[str, Any], key: str) -> None:
    state["lastErrors"].pop(key, None)


def _youtube_episodes(source_id: str) -> list[tuple[Path, dict[str, Any]]]:
    out = []
    for path in list_episode_files(source_id):
        episode = read_json(path)
        if str(episode.get("guid", "")).startswith(GUID_PREFIX):
            out.append((path, episode))
    return out


def _title(episode: dict[str, Any]) -> str:
    return episode.get("title") or episode["guid"]


# ===== étapes ================================================================
def detecter(source_id: str, notify: Notify,
             fetch: Callable[[str], Any] = fetch_youtube_episodes) -> int:
    result = fetch(source_id)
    titles = {ep["guid"]: _title(ep) for _, ep in _youtube_episodes(source_id)}
    for guid in result.created:
        notify(f"🎙️ Nouvel épisode détecté : {titles.get(guid, guid)}. "
               "Transcription en cours.")
    for video in result.unrecognized:
        notify(f"❓ Vidéo non reconnue sur la chaîne : « {video['title']} » "
               f"https://www.youtube.com/watch?v={video['id']}\n"
               "Si c'est un épisode, son titre n'a pas le format attendu "
               "(suffixe du podcast et « S<saison>-E<numéro> ») : rien n'a été traité.")
    return 0


def _remove_audio(source_id: str, guid: str) -> None:
    """L'audio se retélécharge : inutile de garder ~70 Mo par épisode (ni de les sauvegarder)."""
    folder = common.AUDIO_DIR / source_id
    for path in folder.glob(f"{slugify(guid)}*"):
        with contextlib.suppress(OSError):
            path.unlink()


def transcrire(source_id: str, notify: Notify, state: dict[str, Any],
               transcriber: Callable[..., Any] | None = None,
               model: str = WHISPER_MODEL) -> int:
    if transcriber is None:
        from transcribe import transcribe_episode as transcriber
    for path, episode in _youtube_episodes(source_id):
        if episode.get("transcriptStatus", "none") != "none":
            continue
        key = f"transcription:{episode['guid']}"
        try:
            transcriber(source_id, path, model, "fr", False)
        except Exception as exc:  # noqa: BLE001 — l'épisode suivant doit passer quand même.
            _report_once(state, key,
                         f"⚠️ Transcription impossible pour « {_title(episode)} » : {exc}",
                         notify)
            continue
        _clear_error(state, key)
        _remove_audio(source_id, episode["guid"])
    return 0


def a_extraire(source_id: str, state: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (path, episode) for path, episode in _youtube_episodes(source_id)
        if episode.get("transcriptStatus") in {"auto", "validated"}
        and episode["guid"] not in state["extracted"]
        and transcript_path_for(source_id, episode["guid"]).exists()
    ]


def _pipeline_lock() -> contextlib.AbstractContextManager[None]:
    from review_lock import acquire_pipeline_lock
    return acquire_pipeline_lock(force=False)


def extraire(source_id: str, notify: Notify, state: dict[str, Any], *,
             review_url: str,
             client_factory: Callable[[], Any] | None = None,
             extractor: Callable[..., int] | None = None,
             lock: Callable[[], contextlib.AbstractContextManager[None]] = _pipeline_lock,
             model: str | None = None) -> int:
    pending = a_extraire(source_id, state)
    if not pending:
        return 0
    if client_factory is None:
        from common import make_anthropic_client as client_factory
    if extractor is None:
        from extract_recos import extract_for_episode as extractor
    if model is None:
        from extract_recos import MODEL as model

    try:
        client = client_factory()
    except Exception as exc:  # noqa: BLE001
        _report_once(state, "extraction:client", f"⚠️ Extraction impossible : {exc}", notify)
        return 1
    _clear_error(state, "extraction:client")

    from review_lock import LockBusy
    try:
        with lock():
            _clear_error(state, "extraction:verrou")
            source = load_source(source_id)
            for path, episode in pending:
                _extract_one(source_id, path, episode, state, notify, client=client,
                             extractor=extractor, model=model, source=source,
                             review_url=review_url)
    except LockBusy as exc:
        _report_once(state, "extraction:verrou",
                     f"⚠️ Extraction repoussée, la page de validation tient le verrou : {exc}",
                     notify)
        return 1
    return 0


def _extract_one(source_id: str, path: Path, episode: dict[str, Any],
                 state: dict[str, Any], notify: Notify, **kwargs: Any) -> None:
    guid = episode["guid"]
    key = f"extraction:{guid}"
    try:
        count = kwargs["extractor"](source_id, path, kwargs["client"], False,
                                    model=kwargs["model"], source=kwargs["source"])
    except Exception as exc:  # noqa: BLE001
        _report_once(state, key,
                     f"⚠️ Extraction impossible pour « {_title(episode)} » : {exc}", notify)
        return
    _clear_error(state, key)
    state["extracted"].append(guid)
    link = f"{kwargs['review_url'].rstrip('/')}/ep?guid={urllib.parse.quote(guid, safe='')}"
    notify(f"✅ {_title(episode)} : {count} reco(s) à valider.\n{link}")


# ===== notification ==========================================================
def build_notify(channel: str) -> Notify:
    sender = None
    if channel != "none":
        from poll_rss import _build_sender
        sender = _build_sender(channel)

    def notify(text: str) -> None:
        log.info("Notification : %s", text)
        if sender is not None:
            sender.send({"msgtype": "m.text", "body": text})

    return notify


# ===== CLI ===================================================================
STEPS = ("detecter", "transcrire", "a-extraire", "extraire")


@contextlib.contextmanager
def _state(source_id: str) -> Iterator[dict[str, Any]]:
    state = load_state(source_id)
    try:
        yield state
    finally:
        save_state(source_id, state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chaîne automatique d'un nouvel épisode.")
    parser.add_argument("etape", choices=STEPS)
    parser.add_argument("--source", required=True)
    parser.add_argument("--notify", default=os.environ.get("RECO_NOTIFY", "matrix"),
                        help="matrix | discord | slack | email | none (défaut: %(default)s)")
    parser.add_argument("--review-url",
                        default=os.environ.get("RECO_REVIEW_URL", DEFAULT_REVIEW_URL),
                        help="Adresse de la page de validation, pour les liens.")
    parser.add_argument("--modele-transcription", default=WHISPER_MODEL)
    args = parser.parse_args(argv)

    if args.etape == "a-extraire":
        pending = a_extraire(args.source, load_state(args.source))
        log.info("%d épisode(s) à extraire.", len(pending))
        return 0 if pending else 1

    notify = build_notify(args.notify)
    if args.etape == "detecter":
        return detecter(args.source, notify)
    with _state(args.source) as state:
        if args.etape == "transcrire":
            return transcrire(args.source, notify, state, model=args.modele_transcription)
        return extraire(args.source, notify, state, review_url=args.review_url)


if __name__ == "__main__":
    sys.exit(main())
