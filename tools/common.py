"""
common.py — Utilitaires partagés du pipeline de collecte « Reco ».

Centralise :
  - la résolution des chemins du projet (racine, dossiers de contenu, sorties) ;
  - la lecture des sources (podcasts) ;
  - la lecture / écriture *idempotente* des fichiers JSON conformes au schéma ;
  - la fabrication d'identifiants stables (slug, prefixe de reco) ;
  - les helpers texte/timestamp/YouTube partagés ;
  - un logger simple et homogène pour tous les scripts.

Tout le pipeline écrit en UTF-8 (accents français corrects) et n'écrit un
fichier que si son contenu a réellement changé (idempotence).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

# --- Chemins du projet ------------------------------------------------------
# common.py vit dans <racine>/tools/ ; la racine du projet est donc le parent.
TOOLS_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = TOOLS_DIR.parent

# C1 (revue 2026-07-19) — garantir la RACINE du projet sur sys.path. Un script
# lancé en standalone (`python tools/x.py`) n'a que `tools/` sur le path ; sans
# la racine, les imports `from tools.config…` (reco_prefix, et le package
# `config` lui-même en interne) plantent → /add-reco et l'extraction tombaient
# en 500 « comme documenté ». common.py étant importé en premier par tous les
# scripts, ce bootstrap répare toute la chaîne. Idempotent, sans effet en mode
# package (racine déjà présente via pytest / `python -m`).
#
# M3 (revue 2026-07-19) — CONSÉQUENCE CONNUE ET BÉNIGNE : comme `tools/` est
# aussi sur sys.path (pyproject `pythonpath`) et qu'il n'y a pas de
# `tools/__init__.py`, common.py est importable sous DEUX noms — `common` (plat)
# et `tools.common` (paquet, via config.loader) — donc chargé deux fois. Sans
# effet en prod (mêmes chemins, logger partagé par le registre logging global).
# Le seul piège est côté tests : monkeypatcher `common.SOURCES_DIR` n'affecte pas
# le code lisant `tools.common.*` ; les tests concernés patchent donc déjà
# `config.loader`/`config.registry` directement. Uniformiser les imports (tout
# `tools.x` ou tout plat) supprimerait la duplication mais imposerait un refactor
# sur ~180 fichiers pour un défaut sans impact → volontairement NON fait.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CONTENT_DIR: Path = PROJECT_ROOT / "src" / "content"
SOURCES_DIR: Path = CONTENT_DIR / "sources"
EPISODES_DIR: Path = CONTENT_DIR / "episodes"
RECOS_DIR: Path = CONTENT_DIR / "recos"

# Sorties propres au pipeline (transcriptions, audio temporaire) — hors src/.
OUTPUT_DIR: Path = TOOLS_DIR / "output"
TRANSCRIPTS_DIR: Path = OUTPUT_DIR / "transcripts"
AUDIO_DIR: Path = OUTPUT_DIR / "audio"


# --- Regex pré-compilées ----------------------------------------------------
_RE_YT_ID = re.compile(r"[?&]v=([A-Za-z0-9_-]+)")
_RE_NON_ALNUM_SPACE = re.compile(r"[^a-z0-9 ]+")
_RE_WHITESPACE = re.compile(r"\s+")
_RE_SLUG_NONALNUM = re.compile(r"[^a-z0-9]+")
_RE_SLUG_NONALNUM_STRICT = re.compile(r"[^a-z0-9]")


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
    value = _RE_SLUG_NONALNUM.sub("-", value).strip("-")
    return value or "x"


def reco_prefix(source_id: str) -> str:
    """Préfixe court pour les ID de recos d'une source (SSOT = config JSON).

    La valeur vient EXCLUSIVEMENT de ``src/content/sources/<id>.json``
    (champ ``recoPrefix``). L'heuristique historique (initiales du slug)
    a été retirée (issue #14) car elle masquait silencieusement les
    sources mal configurées et empêchait de vérifier que les IDs de
    recos sont stables dans le temps.

    Raises:
        FileNotFoundError: si aucune config n'existe pour ``source_id``.
            Le message indique le chemin attendu.
    """
    # Import paresseux OBLIGATOIRE : `tools.config.loader.DEFAULT_SOURCES_DIR`
    # importe `tools.common.PROJECT_ROOT`, donc un import top-level créerait
    # un cycle d'import.
    # (Racine du repo garantie sur sys.path par le bootstrap C1 en tête de
    # module → ces imports package fonctionnent aussi en standalone.)
    from tools.config.loader import ConfigLoadError  # noqa: PLC0415
    from tools.config.registry import get_source  # noqa: PLC0415
    try:
        return get_source(source_id).reco_prefix
    except ConfigLoadError as exc:
        raise FileNotFoundError(
            f"Pas de config pour la source « {source_id} » — "
            f"impossible de déterminer le préfixe reco. ({exc})"
        ) from exc


# --- Helpers texte ----------------------------------------------------------
def normalize_text(s: str | None) -> str:
    """Normalisation robuste pour l'appariement (sans accent, casse, ponct.).

    Contrairement à `slugify`, ne remplace pas les espaces par des tirets : le
    résultat reste un texte lisible utilisable pour comparaison ou recherche.
    """
    if not s:
        return ""
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _RE_NON_ALNUM_SPACE.sub(" ", s)
    return _RE_WHITESPACE.sub(" ", s).strip()


# --- Helpers YouTube --------------------------------------------------------
def extract_youtube_id(url: str | None) -> str | None:
    """Extrait l'identifiant d'une URL YouTube (watch?v=…). None si introuvable."""
    if not url:
        return None
    m = _RE_YT_ID.search(url)
    return m.group(1) if m else None


def download_youtube_thumbnail(video_id: str) -> bytes | None:
    """Télécharge la miniature YouTube (maxres puis hq en repli).

    Renvoie les octets de l'image, ou None si rien d'exploitable n'est trouvé.
    Les images < 2000 octets sont considérées comme des placeholders (404 JPG
    transparent renvoyé par YouTube). Timeout 30 s, gère les RequestException.
    """
    try:
        import requests  # noqa: PLC0415 — import paresseux.
    except ImportError:  # pragma: no cover
        return None
    for quality in ("maxresdefault", "hqdefault"):
        url = f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
        try:
            resp = requests.get(url, timeout=30)
        except requests.exceptions.RequestException:
            continue
        if resp.status_code == 200 and len(resp.content) >= 2000:
            return resp.content
    return None


# --- Helpers timestamps -----------------------------------------------------
def format_timestamp(seconds: float | int) -> str:
    """Formate un nombre de secondes en « HH:MM:SS »."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_timestamp(ts: str | None) -> int | None:
    """Convertit un timestamp « HH:MM:SS » / « MM:SS » / « SS » en secondes.

    Renvoie None si la chaîne est vide ou ne peut être parsée.
    """
    if not ts:
        return None
    try:
        parts = [int(x) for x in ts.split(":")]
    except (ValueError, AttributeError):
        return None
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


def episode_label(season: int | None, number: int | None) -> str:
    """Étiquette compacte d'un épisode : « S5E12 », « #42 » ou chaîne vide."""
    if season and number:
        return f"S{season}E{number}"
    if number:
        return f"#{number}"
    return ""


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
    """Sérialise en JSON lisible, UTF-8, accents conservés, clés triées stables."""
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Écrit `text` dans `path` de façon atomique : write tmp → fsync → replace.

    Centralisation de la stratégie originellement vivant dans
    `reco_dedup_merge._atomic_write_json` — partagée maintenant entre
    `common.write_json_if_changed` (pipeline + serveur) et le handler
    `_allocate_new_reco` (review_routes) pour éviter qu'un lecteur tombe
    sur un fichier tronqué pendant l'écriture.

    Stratégie :
      - écrit dans `<path>.tmp` dans le même dossier (rename atomique),
      - flush + fsync pour garantir bytes sur disque AVANT rename,
      - os.replace (atomique POSIX ; sur Windows, retry 4× si un autre
        processus tient un handle ouvert sur la cible — cas typique du
        reviewer qui lit pendant que l'enricher écrit).
      - cleanup du `.tmp` en cas d'échec.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # Windows : un lecteur tenant un handle ouvert sur `path` pose un
        # PermissionError sur os.replace. On retente 4× (la dernière laisse
        # remonter l'exception). 100 ms x 4 = 400 ms max — borné, et le
        # cas est rare en single-utilisateur.
        for i in range(4):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if i == 3:
                    raise
                time.sleep(0.1)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def write_json_if_changed(path: Path, data: dict[str, Any]) -> bool:
    """
    Écrit `data` en JSON dans `path` UNIQUEMENT si le contenu diffère du fichier
    existant. Renvoie True si une écriture a eu lieu, False sinon (idempotence).

    L'écriture est ATOMIQUE (tmp + fsync + os.replace) pour qu'un lecteur
    concurrent (typiquement review_server) ne tombe jamais sur un fichier
    tronqué — protection contre `ValueError` au milieu d'une écriture
    pipeline.
    """
    new_text = _serialize(data)
    if path.exists():
        try:
            old_text = path.read_text(encoding="utf-8")
        except OSError:
            old_text = None
        if old_text == new_text:
            return False
    atomic_write_text(path, new_text)
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


def find_episode_by_guid(source_id: str, guid: str) -> Path:
    """Retrouve le fichier JSON d'un épisode par son guid.

    Centralisé ici pour éviter la duplication dans transcribe / extract_recos /
    compare_models. Lève FileNotFoundError si aucun épisode ne correspond.
    """
    for path in list_episode_files(source_id):
        if read_json(path).get("guid") == guid:
            return path
    raise FileNotFoundError(
        f"Aucun épisode avec guid « {guid} » dans la source « {source_id} »."
    )


# --- Clients API (imports paresseux) ---------------------------------------
# Centralisé ici pour éviter le couplage entre scripts frères qui partageaient
# l'usage du même client Anthropic (ocr_thumbnails, rematch_with_ocr, etc.)
def make_anthropic_client():
    """Initialise un client Anthropic.

    Lit `ANTHROPIC_API_KEY` depuis `tools/.env` (via python-dotenv) ou
    l'environnement. Import du SDK paresseux pour ne pas l'imposer aux scripts
    qui n'en ont pas besoin (ex. fetch_episodes).
    """
    try:
        import anthropic  # noqa: PLC0415 — import paresseux.
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Le SDK anthropic n'est pas installé (pip install -r requirements.txt)."
        ) from exc
    from dotenv import load_dotenv  # noqa: PLC0415 — import paresseux.
    import os  # noqa: PLC0415
    load_dotenv(TOOLS_DIR / ".env")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Variable d'environnement ANTHROPIC_API_KEY manquante. "
            "Copie tools/.env.example en tools/.env et renseigne la clé, "
            "ou exporte-la dans ton shell."
        )
    return anthropic.Anthropic(api_key=api_key)


def make_openai_client():
    """Initialise un client OpenAI. Cf. `make_anthropic_client` pour le pattern."""
    try:
        import openai  # noqa: PLC0415 — import paresseux.
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Le SDK openai n'est pas installé (pip install openai)."
        ) from exc
    from dotenv import load_dotenv  # noqa: PLC0415 — import paresseux.
    import os  # noqa: PLC0415
    load_dotenv(TOOLS_DIR / ".env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Variable d'environnement OPENAI_API_KEY manquante.")
    return openai.OpenAI(api_key=api_key)
