"""
common.py — Utilitaires partagés du pipeline de collecte « Reco ».

Centralise :
  - la résolution des chemins du projet (racine, dossiers de contenu, sorties) ;
  - la lecture des sources (podcasts) ;
  - la lecture / écriture *idempotente* des fichiers JSON conformes au schéma ;
  - la fabrication d'identifiants stables (slug, prefixe de reco) ;
  - un logger simple et homogène pour tous les scripts.

Tout le pipeline écrit en UTF-8 (accents français corrects) et n'écrit un
fichier que si son contenu a réellement changé (idempotence).
"""

from __future__ import annotations

import json
import logging
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

# --- Chemins du projet ------------------------------------------------------
# common.py vit dans <racine>/tools/ ; la racine du projet est donc le parent.
TOOLS_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = TOOLS_DIR.parent

CONTENT_DIR: Path = PROJECT_ROOT / "src" / "content"
SOURCES_DIR: Path = CONTENT_DIR / "sources"
EPISODES_DIR: Path = CONTENT_DIR / "episodes"
RECOS_DIR: Path = CONTENT_DIR / "recos"

# Sorties propres au pipeline (transcriptions, audio temporaire) — hors src/.
OUTPUT_DIR: Path = TOOLS_DIR / "output"
TRANSCRIPTS_DIR: Path = OUTPUT_DIR / "transcripts"
AUDIO_DIR: Path = OUTPUT_DIR / "audio"


# --- Logging ----------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    """Renvoie un logger configuré (console, niveau INFO) et idempotent."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Sur Windows, la console est souvent en cp1252 : on force l'UTF-8 pour
        # que les accents et symboles ne provoquent pas d'UnicodeEncodeError.
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


log = get_logger("reco")


# --- Slugs & identifiants ---------------------------------------------------
def slugify(value: str) -> str:
    """Transforme un texte en slug ASCII minuscule (pour noms de fichiers)."""
    # Décompose les accents puis retire les diacritiques.
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "x"


def reco_prefix(source_id: str) -> str:
    """
    Préfixe court pour les ID de recos d'une source.

    Convention observée dans les données d'exemple : « un-bon-moment » -> « ubm ».
    On prend l'initiale de chaque segment du slug ; si une seule lettre, on
    complète avec les premières lettres du slug pour rester lisible.
    """
    segments = [s for s in source_id.split("-") if s]
    initials = "".join(s[0] for s in segments)
    if len(initials) >= 2:
        return initials
    # Repli : 3 premiers caractères alphanumériques.
    return re.sub(r"[^a-z0-9]", "", source_id)[:3] or "rec"


# --- Lecture des sources ----------------------------------------------------
def load_source(source_id: str) -> dict[str, Any]:
    """Charge `src/content/sources/<id>.json` ou lève FileNotFoundError."""
    path = SOURCES_DIR / f"{source_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Source introuvable : {path}. "
            f"Vérifie l'identifiant (--source) et le dossier sources/."
        )
    return read_json(path)


# --- JSON I/O idempotent ----------------------------------------------------
def read_json(path: Path) -> dict[str, Any]:
    """Lit un fichier JSON UTF-8."""
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _serialize(data: dict[str, Any]) -> str:
    """Sérialise en JSON lisible, UTF-8, accents conservés, clé triée stable."""
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def write_json_if_changed(path: Path, data: dict[str, Any]) -> bool:
    """
    Écrit `data` en JSON dans `path` UNIQUEMENT si le contenu diffère du fichier
    existant. Renvoie True si une écriture a eu lieu, False sinon (idempotence).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    new_text = _serialize(data)
    if path.exists():
        old_text = path.read_text(encoding="utf-8")
        if old_text == new_text:
            return False
    path.write_text(new_text, encoding="utf-8")
    return True


def episodes_dir_for(source_id: str) -> Path:
    """Dossier des épisodes d'une source."""
    return EPISODES_DIR / source_id


def recos_dir_for(source_id: str) -> Path:
    """Dossier des recos d'une source."""
    return RECOS_DIR / source_id


def transcript_path_for(source_id: str, guid: str) -> Path:
    """Chemin de la transcription texte d'un épisode (clé = guid)."""
    return TRANSCRIPTS_DIR / source_id / f"{slugify(guid)}.txt"


def list_episode_files(source_id: str) -> list[Path]:
    """Liste triée des fichiers JSON d'épisodes d'une source."""
    d = episodes_dir_for(source_id)
    if not d.exists():
        return []
    return sorted(d.glob("*.json"))
