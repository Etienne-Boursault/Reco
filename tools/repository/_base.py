"""
_base.py — Helpers communs aux repositories JSON (`ItemRepoJson`,
`MentionRepoJson`).

Centralise les patterns redondants : validation `source_id`, validation
`id` court, lecture défensive d'un fichier JSON, écriture atomique +
idempotente. Tout repo concret peut hériter ou composer.

Pure logique de mapping/IO local — zéro dépendance domaine sauf pour
le typing (les codecs sont passés en paramètre).
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from common import atomic_write_text


# Slug court d'identité d'entité (item_id, mention_id). Aligné sur
# `Item.id` côté domaine.
_ID_PATTERN = re.compile(r"^[a-z0-9-]{1,64}$")

# Slug `source_id` — cohérent avec `tools/config/schema.py::_RE_ID`.
# Empêche le path-traversal (`..`, `/`, `\\`, etc.).
_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_id(entity: str, value: str) -> None:
    """Valide un id court d'entité ou lève ValueError contextualisée."""
    if not isinstance(value, str) or not _ID_PATTERN.match(value):
        raise ValueError(
            f"{entity} invalide: {value!r}; attendu ^[a-z0-9-]{{1,64}}$"
        )


def validate_source_id(value: str) -> None:
    """Valide un `source_id` (slug podcast). Première ligne de défense
    contre la traversée de chemin (`../`, `/abs/path`, etc.)."""
    if not isinstance(value, str) or not _SOURCE_ID_PATTERN.match(value):
        raise ValueError(
            f"source_id invalide: {value!r}; "
            "attendu ^[a-z0-9]+(-[a-z0-9]+)*$"
        )


T = TypeVar("T")


def load_json_safely(
    path: Path,
    from_dict: Callable[[dict[str, Any]], T],
) -> T | None:
    """Lecture défensive d'un fichier JSON.

    Politique : un fichier corrompu / illisible → None, jamais une exception
    (les outils d'audit signaleront — la lecture ne casse pas le pipeline).
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return from_dict(data)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def write_json_idempotent(
    path: Path,
    payload: dict[str, Any],
) -> bool:
    """Sérialise `payload` (JSON canonique) et écrit atomically.

    Idempotent : si le contenu disque est déjà sémantiquement identique
    (dict désérialisé == payload), on ne ré-écrit pas — utile pour éviter
    de polluer mtime/git quand l'`indent` ou l'ordre des clés diffère.

    Renvoie True si écriture, False si no-op.

    Politique d'encodage : `indent=2 + sort_keys=True + trailing newline +
    LF` (cf. ADR 0009).
    """
    new_text = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8")
            # Comparaison textuelle exacte d'abord (rapide, gère 99% des cas).
            if existing == new_text:
                return False
            # Comparaison sémantique : permet de tolérer indent / sort_keys
            # variant tant que la donnée reste la même.
            try:
                if json.loads(existing) == payload:
                    return False
            except (ValueError, json.JSONDecodeError):
                pass
        except OSError:
            pass
    atomic_write_text(path, new_text)
    return True


__all__ = [
    "validate_id",
    "validate_source_id",
    "load_json_safely",
    "write_json_idempotent",
]
