"""
transcription_mesures.py — ce que la télémétrie retient d'une transcription.

Séparé de `transcribe.py` pour que celui-ci ne porte que des points de mesure
d'une ligne. Tout s'écrit dans l'étape courante (`telemetry.current_stage()`),
qui n'écrit rien hors d'un run.

Ce qui n'est PAS confondu :
  - la durée de l'audio (`media_duration_ms`, mesurée par le décodeur) et la
    durée du calcul (`transcribe_ms`) ;
  - le chargement du modèle (`model_load_ms`), la transcription longue
    (`transcribe_ms`) et la réécoute des trous (`gap_repair_ms`), chronométrés
    séparément — jamais le même chrono recopié ;
  - un audio réutilisé (`audio_cache_hit`) et un audio téléchargé.

L'URL du média n'est jamais gardée : l'identifiant d'une vidéo YouTube est
public ; une URL Acast peut porter des paramètres, on n'en garde qu'une empreinte.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from importlib import metadata
from pathlib import Path
from typing import Any

import combler_trous
import telemetry

ENGINE = "faster-whisper"
_YOUTUBE_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})")


def ms_depuis(debut_ns: int) -> int:
    return (time.perf_counter_ns() - debut_ns) // 1_000_000


def _version(paquet: str) -> str | None:
    try:
        return metadata.version(paquet)
    except metadata.PackageNotFoundError:
        return None


def saison(episode: dict[str, Any]) -> int | None:
    """La saison écrite dans l'épisode, jamais devinée (ni d'un titre, ni d'un guid)."""
    valeur = episode.get("season")
    return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) else None


def configuration(model: str, language: str | None, amorce: str | None,
                  prefer_acast: bool) -> dict[str, Any]:
    """Paramètres fonctionnels de la transcription (empreinte de configuration).

    L'amorce compte par sa seule présence : son texte cite le titre de
    l'épisode et changerait l'empreinte à chaque épisode.
    """
    return {
        "engine": ENGINE, "engine_version": _version("faster-whisper"),
        "ctranslate2_version": _version("ctranslate2"),
        "model": model, "device": "cpu", "compute_type": "int8", "beam_size": 5,
        "vad_filter": True, "language": language, "amorce": bool(amorce),
        "media_preference": "acast" if prefer_acast else "youtube",
        "cpu_threads": os.environ.get("OMP_NUM_THREADS") or "auto",
        "gap_repair": {"saut_min_s": combler_trous.SAUT_MIN,
                       "fenetre_min_s": combler_trous.FENETRE_MIN,
                       "recouvrement_min": combler_trous.RECOUVREMENT_MIN},
    }


def _taille(fichier: Path) -> int | None:
    try:
        return fichier.stat().st_size
    except OSError:
        return None


def telechargement(fichier: Path, debut_ns: int) -> None:
    etape = telemetry.current_stage()
    etape.measure("audio_cache_hit", False, "bool")
    etape.measure("download_ms", ms_depuis(debut_ns), "ms")
    etape.measure("download_bytes", _taille(fichier), "bytes")


def _empreinte_fichier(fichier: Path) -> str | None:
    """Empreinte du fichier ; None s'il est illisible (une mesure ne casse rien)."""
    h = hashlib.sha256()
    try:
        with fichier.open("rb") as fh:
            for bloc in iter(lambda: fh.read(1 << 20), b""):
                h.update(bloc)
    except OSError:
        return None
    return f"sha256:{h.hexdigest()}"


def identifiant_media(episode: dict[str, Any], origine: str) -> str | None:
    if origine == "youtube":
        trouve = _YOUTUBE_ID.search(episode.get("youtubeUrl") or "")
        return f"youtube:{trouve.group(1)}" if trouve else None
    url = (episode.get("audioUrl") or "").split("?")[0]
    if not url:
        return None
    return f"{origine}:url-sha256:{hashlib.sha256(url.encode()).hexdigest()[:16]}"


def media(etape: telemetry.StageHandle, episode: dict[str, Any], audio: Path,
          origine: str) -> None:
    """Origine RÉELLEMENT utilisée (pas l'option demandée) et identité du fichier.

    L'empreinte de l'audio coûte une lecture du fichier (~70 Mo, une fraction de
    seconde) face à un quart d'heure de transcription : elle est calculée.
    """
    origine = origine if origine in {"youtube", "acast"} else "other"
    etape.set(media_origin=origine, media_identifier=identifiant_media(episode, origine),
              media_checksum=_empreinte_fichier(audio))
    etape.measure("audio_bytes", _taille(audio), "bytes")


def transcription(etape: telemetry.StageHandle, info: Any, debut_ns: int) -> None:
    etape.measure("transcribe_ms", ms_depuis(debut_ns), "ms")
    duree = getattr(info, "duration", None)
    if isinstance(duree, int | float):
        etape.set(media_duration_ms=round(duree * 1000))
    parole = getattr(info, "duration_after_vad", None)
    if isinstance(parole, int | float):
        etape.measure("speech_duration_ms", round(parole * 1000), "ms")
    etape.measure("language_detected", getattr(info, "language", None), "iso639-1")
    etape.measure("language_probability", getattr(info, "language_probability", None),
                  "ratio")


def comblement(etape: telemetry.StageHandle, bilan: Any, debut_ns: int) -> None:
    """Réécoute des trous : son temps propre, et ce qu'elle a retrouvé."""
    etape.measure("gap_repair_ms", ms_depuis(debut_ns), "ms")
    etape.measure("gap_candidates", bilan.candidats, "count")
    etape.measure("gaps_filled", bilan.combles, "count")
    etape.measure("gap_words_added", bilan.mots_ajoutes, "count")
    etape.measure("gaps_unfilled", len(bilan.non_combles), "count")


def empreinte_texte(texte: str) -> str:
    return f"sha256:{hashlib.sha256(texte.encode('utf-8')).hexdigest()}"
