"""Loader de `SourceConfig` — couche IO.

SRP : ce module ne fait que ``lire un fichier JSON disque → SourceConfig``.
Toute erreur (fichier manquant, JSON invalide, schéma invalide) est
encapsulée dans `ConfigLoadError` avec un message actionnable.

Note : la règle de cohérence "filename ↔ id payload" vit dans
``SourceConfig.from_dict(expected_id=...)`` côté schéma — le loader se
contente de passer ``source_id`` (qui vient du nom de fichier).
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.config.schema import SourceConfig

__all__ = ["ConfigLoadError", "DEFAULT_SOURCES_DIR", "load_source_config"]

# Dossier par défaut — SSOT partagée avec Astro (collection `sources`).
# On résout depuis ``common.PROJECT_ROOT`` pour ne pas dupliquer la traversée
# de chemin (`Path(__file__).parent.parent.parent`).
def _default_sources_dir() -> Path:
    # Import paresseux : ``common`` importe potentiellement d'autres modules
    # (logging setup). On le tape uniquement au premier accès.
    try:
        from tools.common import PROJECT_ROOT  # noqa: PLC0415
    except ImportError:  # pragma: no cover — fallback si common indisponible
        return Path(__file__).resolve().parent.parent.parent / "src" / "content" / "sources"
    return PROJECT_ROOT / "src" / "content" / "sources"


DEFAULT_SOURCES_DIR: Path = _default_sources_dir()


class ConfigLoadError(RuntimeError):
    """Erreur de chargement d'une config source (chemin/JSON/validation)."""


def load_source_config(
    source_id: str,
    sources_dir: Path | None = None,
) -> SourceConfig:
    """Charge ``<sources_dir>/<source_id>.json`` → `SourceConfig`.

    Args:
        source_id: identifiant de la source (ex. ``un-bon-moment``).
        sources_dir: dossier des configs. Défaut = `DEFAULT_SOURCES_DIR`.

    Raises:
        ConfigLoadError: si fichier introuvable, JSON cassé, ou schéma
            invalide. Le message d'erreur précise toujours le chemin.
    """
    root = sources_dir if sources_dir is not None else DEFAULT_SOURCES_DIR
    path = root / f"{source_id}.json"

    if not path.exists():
        raise ConfigLoadError(
            f"Configuration source introuvable : {path}. "
            f"Vérifie l'identifiant (« {source_id} ») et le dossier sources/."
        )

    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(
            f"JSON invalide dans {path} : {exc.msg} (ligne {exc.lineno})."
        ) from exc

    try:
        return SourceConfig.from_dict(payload, expected_id=source_id)
    except (ValueError, TypeError) as exc:
        # id mismatch est un cas d'erreur de cohérence fichier ↔ contenu :
        # on rend l'origine (path.name) visible dans le message.
        msg = str(exc)
        if "mismatch" in msg.lower():
            raise ConfigLoadError(
                f"id mismatch dans {path.name} : {msg}. "
                f"Renomme le fichier ou corrige l'id."
            ) from exc
        raise ConfigLoadError(
            f"Configuration invalide dans {path} : {exc}"
        ) from exc
