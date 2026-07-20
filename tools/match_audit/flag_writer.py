"""Écrit/efface le flag ``matchSuspect`` (miroir bool dans le JSON d'épisode).

Le détail des suspicions vit dans le sidecar (cf. ``sidecar.py``). Ici on
ne touche QU'à un booléen, miroir pour Astro / consommateurs UI.

CR senior C5 — **idempotence stricte** : on N'utilise PAS
``common.write_json_if_changed`` (qui re-sérialise avec ``sort_keys=True``
et casserait l'ordre des clés au premier ``--apply``). On lit le texte
brut, on compare aux octets attendus avec l'ordre des clés PRÉSERVÉ, et on
n'écrit que si le contenu logique a changé.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import common  # type: ignore[attr-defined]


class CommonEpisodeRepo:
    """Adaptateur ``EpisodeRepo`` qui s'appuie sur ``common.*``.

    Découple flag_writer de l'import direct (DIP — CR senior H2).
    """

    def load(self, path: Path) -> dict[str, Any]:
        return common.read_json(path)

    def save_if_changed(self, path: Path, data: Mapping[str, Any]) -> bool:
        return _write_preserving_order(path, dict(data))


def _serialize_preserving_order(data: Mapping[str, Any]) -> str:
    """Sérialise SANS ``sort_keys=True`` — ordre des clés conservé."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _write_preserving_order(path: Path, data: Mapping[str, Any]) -> bool:
    """Écrit ``data`` dans ``path`` si le contenu logique a changé.

    Compare au niveau **texte** (octets) AVEC l'ordre des clés courant,
    pas via sort_keys (cf. CR senior C5). Si le texte est identique au
    fichier existant, on ne fait rien (idempotence).

    Écriture atomique (tmp + fsync + replace) via
    ``common.atomic_write_text``.
    """
    new_text = _serialize_preserving_order(data)
    if path.exists():
        try:
            old_text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover — defensive
            old_text = None
        if old_text == new_text:
            return False
    common.atomic_write_text(path, new_text)
    return True


def set_match_suspect_flag(
    path: Path,
    suspect: bool,
    *,
    repo: CommonEpisodeRepo | None = None,
) -> bool:
    """Met à jour ``episode.matchSuspect``.

    - ``suspect=True`` : ajoute ``matchSuspect: true`` si absent ou ≠ true.
    - ``suspect=False`` : retire le champ s'il existe (pas de stockage de
      ``false`` pour garder le JSON minimal — Zod accepte l'absence).

    Retourne True si une écriture a eu lieu, False si idempotent.
    """
    r = repo or CommonEpisodeRepo()
    data = r.load(path)
    current = data.get("matchSuspect")
    if suspect:
        if current is True:
            return False
        data["matchSuspect"] = True
    else:
        if "matchSuspect" not in data:
            return False
        del data["matchSuspect"]
    return r.save_if_changed(path, data)


def clear_match_suspect_flag(
    path: Path, *, repo: CommonEpisodeRepo | None = None,
) -> bool:
    """Helper : retire ``matchSuspect`` (équivaut à ``set_match_suspect_flag(False)``).

    Exposé publiquement (CR archi #21) pour le ``--undo-last`` et les
    workflows qui veulent juste nettoyer.
    """
    return set_match_suspect_flag(path, False, repo=repo)


__all__ = [
    "CommonEpisodeRepo",
    "clear_match_suspect_flag",
    "set_match_suspect_flag",
]
