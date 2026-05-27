"""
transcribe.py — Étape 2 du pipeline « Reco ».

Pour un épisode donné (identifié par son guid, ou tous les épisodes d'une
source) :
  1. télécharge l'audio depuis `audioUrl` (requests), ou via yt-dlp s'il n'y a
     qu'une `youtubeUrl` ;
  2. transcrit l'audio en local avec faster-whisper (CPU par défaut) ;
  3. écrit la transcription dans
     `tools/output/transcripts/<sourceId>/<guid>.txt` avec timestamps ;
  4. met à jour `transcriptStatus="auto"` dans le JSON de l'épisode.

Cache : si la transcription existe déjà (et que --force n'est pas passé), on ne
retranscrit pas. L'audio téléchargé est gardé dans `tools/output/audio/` et
réutilisé.

Dépendances lourdes (faster-whisper, yt-dlp) importées paresseusement pour que
`--help` et les autres scripts ne les exigent pas.

Usage :
    python transcribe.py --source un-bon-moment --guid <GUID>
    python transcribe.py --source un-bon-moment --all [--limit N]
    python transcribe.py --source un-bon-moment --guid <GUID> --model small --force
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from common import (
    AUDIO_DIR,
    find_episode_by_guid,
    format_timestamp,
    list_episode_files,
    log,
    read_json,
    slugify,
    transcript_path_for,
    write_json_if_changed,
)

# Modèle Whisper par défaut : compromis qualité/vitesse pour du français.
DEFAULT_MODEL = "small"
# Taille de chunk de téléchargement (octets).
_CHUNK = 1 << 16
# Acast (et d'autres CDN) renvoient 403 sans User-Agent de navigateur.
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


# Alias historique : délègue à common.format_timestamp.
_format_timestamp = format_timestamp


def _make_http_session() -> requests.Session:
    """Session HTTP avec retry exponentiel (3 essais) sur erreurs transitoires."""
    session = requests.Session()
    retry = Retry(
        total=3, backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "HEAD")),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _download_http(url: str, dest: Path) -> Path:
    """Télécharge un fichier audio HTTP(S) en streaming, avec retries. Renvoie le chemin."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log.info("Audio déjà téléchargé : %s", dest.name)
        return dest
    log.info("Téléchargement de l'audio : %s", url)
    session = _make_http_session()
    with session.get(url, stream=True, timeout=60, headers=_HTTP_HEADERS) as resp:
        resp.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=_CHUNK):
                if chunk:
                    fh.write(chunk)
        tmp.replace(dest)
    log.info("Audio enregistré : %s (%d octets)", dest.name, dest.stat().st_size)
    return dest


def _download_youtube(url: str, dest_base: Path) -> Path:
    """
    Télécharge la piste audio d'une vidéo YouTube via yt-dlp (import paresseux).
    Renvoie le chemin du fichier audio extrait (m4a/mp3).
    """
    try:
        import yt_dlp  # type: ignore  # noqa: PLC0415 — import paresseux volontaire.
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "yt-dlp n'est pas installé. Ajoute-le (pip install yt-dlp) pour "
            "transcrire depuis YouTube."
        ) from exc

    dest_base.parent.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_base.with_suffix("")) + ".%(ext)s"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        # ffmpeg est installé : on extrait directement en mp3.
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
        ],
    }
    log.info("Téléchargement YouTube (audio) : %s", url)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    mp3 = dest_base.with_suffix(".mp3")
    if mp3.exists():
        return mp3
    # Repli : prend le premier fichier produit avec ce préfixe.
    candidates = sorted(dest_base.parent.glob(dest_base.stem + ".*"))
    if not candidates:
        raise RuntimeError("yt-dlp n'a produit aucun fichier audio.")
    return candidates[0]


def _resolve_audio(source_id: str, episode: dict[str, Any],
                   prefer_youtube: bool = False) -> Path:
    """
    Obtient un fichier audio local pour l'épisode (HTTP Acast ou YouTube).

    Si `prefer_youtube` et qu'une vidéo est liée, on transcrit l'audio de la
    VIDÉO : les timecodes sont alors alignés sur la vidéo (offset nul). Cache
    séparé (« <guid>-yt.mp3 ») pour ne pas écraser l'audio Acast.
    """
    guid = episode["guid"]
    audio_url = episode.get("audioUrl")
    youtube_url = episode.get("youtubeUrl")
    base = AUDIO_DIR / source_id / slugify(guid)

    if prefer_youtube and youtube_url:
        return _download_youtube(youtube_url, base.with_name(base.name + "-yt"))
    if audio_url:
        # On garde l'extension d'origine si reconnaissable, sinon .mp3.
        suffix = Path(audio_url.split("?")[0]).suffix or ".mp3"
        return _download_http(audio_url, base.with_suffix(suffix))
    if youtube_url:
        return _download_youtube(youtube_url, base)
    raise ValueError(
        f"L'épisode {guid} n'a ni audioUrl ni youtubeUrl : impossible de transcrire."
    )


def _transcribe_audio(audio_path: Path, model_name: str, language: str | None) -> str:
    """
    Transcrit un fichier audio avec faster-whisper. Renvoie le texte annoté de
    timestamps, un segment par ligne : « [HH:MM:SS] texte ».
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "faster-whisper n'est pas installé. Installe les dépendances "
            "(pip install -r requirements.txt)."
        ) from exc

    log.info("Chargement du modèle Whisper « %s » (CPU, int8)…", model_name)
    # compute_type=int8 : rapide et léger en RAM sur CPU.
    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    log.info("Transcription en cours (cela peut être long)…")
    segments, info = model.transcribe(
        str(audio_path),
        language=language,           # None = détection automatique.
        vad_filter=True,             # Coupe les silences -> plus rapide/propre.
        beam_size=5,
    )
    log.info("Langue détectée : %s (p=%.2f)", info.language, info.language_probability)

    lines: list[str] = []
    for seg in segments:
        ts = _format_timestamp(seg.start)
        lines.append(f"[{ts}] {seg.text.strip()}")
    return "\n".join(lines) + "\n"


def transcribe_episode(source_id: str, episode_path: Path, model_name: str,
                       language: str | None, force: bool,
                       prefer_youtube: bool = False) -> bool:
    """
    Transcrit un épisode (fichier JSON donné). Renvoie True si une transcription
    a été produite (ou si le statut a été mis à jour), False si rien à faire.
    """
    episode = read_json(episode_path)
    guid = episode["guid"]
    transcript_path = transcript_path_for(source_id, guid)

    # Cache : transcription déjà présente.
    if transcript_path.exists() and not force:
        log.info("Transcription déjà présente pour %s — ignorée (cache).", guid)
        # On s'assure tout de même que le statut reflète la réalité.
        if episode.get("transcriptStatus") == "none":
            episode["transcriptStatus"] = "auto"
            write_json_if_changed(episode_path, episode)
        return False

    audio_path = _resolve_audio(source_id, episode, prefer_youtube)
    text = _transcribe_audio(audio_path, model_name, language)

    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_text(text, encoding="utf-8")
    log.info("Transcription écrite : %s", transcript_path)

    # Met à jour le statut sans régresser un éventuel « validated ».
    if episode.get("transcriptStatus") != "validated":
        episode["transcriptStatus"] = "auto"
        write_json_if_changed(episode_path, episode)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Télécharge et transcrit l'audio des épisodes (faster-whisper)."
    )
    parser.add_argument("--source", required=True, help="Identifiant de la source.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--guid", help="Guid de l'épisode à transcrire.")
    group.add_argument("--all", action="store_true",
                       help="Transcrit tous les épisodes de la source.")
    group.add_argument("--guids-file", dest="guids_file",
                       help="Fichier (un guid par ligne) listant les épisodes à transcrire.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Avec --all : limite le nombre d'épisodes.")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Modèle Whisper (défaut: {DEFAULT_MODEL}). "
                             f"Ex: tiny, base, small, medium, large-v3.")
    parser.add_argument("--language", default="fr",
                        help="Langue (défaut: fr). Vide pour détection auto.")
    parser.add_argument("--force", action="store_true",
                        help="Retranscrit même si le cache existe.")
    parser.add_argument("--youtube", action="store_true",
                        help="Transcrit l'audio de la vidéo YouTube (timecodes "
                             "alignés sur la vidéo, offset nul) quand elle existe.")
    args = parser.parse_args()

    language = args.language or None

    if args.guid:
        path = find_episode_by_guid(args.source, args.guid)
        transcribe_episode(args.source, path, args.model, language, args.force, args.youtube)
        return

    # Mode --all ou --guids-file.
    paths = list_episode_files(args.source)
    if args.guids_file:
        wanted = {g.strip() for g in Path(args.guids_file).read_text(encoding="utf-8").splitlines() if g.strip()}
        paths = [p for p in paths if read_json(p).get("guid") in wanted]
    if args.limit is not None:
        paths = paths[: args.limit]
    total = len(paths)
    log.info("%d épisode(s) à transcrire (modèle %s%s).",
             total, args.model, ", audio YouTube" if args.youtube else "")
    for i, path in enumerate(paths, 1):
        title = read_json(path).get("title", path.name)
        try:
            transcribe_episode(args.source, path, args.model, language, args.force, args.youtube)
            log.info("[%d/%d] ✓ %s", i, total, title)
        except Exception as exc:  # noqa: BLE001 — on continue sur l'épisode suivant.
            log.error("[%d/%d] ✗ %s : %s", i, total, title, exc)


if __name__ == "__main__":
    main()
