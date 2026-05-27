"""
compare_models.py — Outil de diagnostic (hors pipeline).

Transcrit le MÊME extrait audio d'un épisode avec plusieurs modèles Whisper,
chronomètre chacun, et écrit les transcriptions côte à côte. Sert à décider si
la montée en gamme du modèle (tiny -> small -> medium) vaut le surcoût de temps.

N'écrit RIEN dans src/content/ : sorties uniquement dans tools/output/compare/.

Usage :
    python compare_models.py --source un-bon-moment --guid <GUID> \
        --start 00:56:00 --duration 210 --models tiny,small,medium
"""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

from common import OUTPUT_DIR, find_episode_by_guid, format_timestamp, log, read_json
from transcribe import _resolve_audio

# Épisode de test par défaut (« avec Hakim Jemili », contient la reco « Mortel »).
DEFAULT_GUID = "108b16ed-a8ec-47ea-afa2-4e8d4e8d09ad"


def _clip_audio(audio: Path, start: str, duration: int, dest: Path) -> Path:
    """Découpe un extrait [start, start+duration] en WAV 16 kHz mono (ffmpeg)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-ss", start, "-t", str(duration),
        "-i", str(audio), "-ar", "16000", "-ac", "1", str(dest),
    ]
    log.info("Découpe de l'extrait : %s (+%ds) -> %s", start, duration, dest.name)
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


def _transcribe_clip(clip: Path, model_name: str, language: str | None) -> tuple[str, float]:
    """Transcrit l'extrait avec un modèle donné. Renvoie (texte, durée_secondes)."""
    from faster_whisper import WhisperModel  # noqa: PLC0415 — import paresseux.

    t0 = time.time()
    log.info("[%s] chargement du modèle…", model_name)
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(clip), language=language, vad_filter=True, beam_size=5)
    lines = [f"[{format_timestamp(seg.start)}] {seg.text.strip()}" for seg in segments]
    elapsed = time.time() - t0
    log.info("[%s] terminé en %.0f s (langue %s).", model_name, elapsed, info.language)
    return "\n".join(lines) + "\n", elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare des modèles Whisper sur un même extrait.")
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--guid", default=DEFAULT_GUID)
    parser.add_argument("--start", default="00:56:00", help="Début de l'extrait (HH:MM:SS).")
    parser.add_argument("--duration", type=int, default=210, help="Durée de l'extrait (s).")
    parser.add_argument("--models", default="tiny,small,medium",
                        help="Modèles à comparer, séparés par des virgules.")
    parser.add_argument("--language", default="fr")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    episode = read_json(find_episode_by_guid(args.source, args.guid))
    audio = _resolve_audio(args.source, episode)  # réutilise l'audio en cache.

    out_dir = OUTPUT_DIR / "compare" / args.guid
    clip = _clip_audio(audio, args.start, args.duration, out_dir / "clip.wav")

    durations: dict[str, float] = {}
    for model_name in models:
        text, elapsed = _transcribe_clip(clip, model_name, args.language or None)
        (out_dir / f"{model_name}.txt").write_text(text, encoding="utf-8")
        durations[model_name] = elapsed

    # Récapitulatif des temps + ratio par minute d'audio.
    log.info("=== Récapitulatif (extrait de %d s) ===", args.duration)
    for model_name in models:
        ratio = durations[model_name] / args.duration
        log.info("  %-8s : %5.0f s  (%.2fx temps réel)", model_name,
                 durations[model_name], ratio)
    log.info("Transcriptions écrites dans : %s", out_dir)


if __name__ == "__main__":
    main()
