"""
loaders.py — Adapters de chargement de dataset vers ``LintContext``
(CR archi #4, #6).

Le composer racine (CLI) instancie un ``JsonDatasetLoader`` avec les
chemins de base, puis demande ``loader.load(source_id) -> LintContext``.
Le service de lint ne sait rien des fichiers — il consomme un
``LintContext`` pur.

H7 : ``_load_jsons`` logge sur stderr les fichiers JSON skippés et
émet un ``LintIssue`` synthétique ``dataset_io`` que le composer pourra
incorporer au rapport.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .rules.base import LintContext, LintIssue, Severity


@runtime_checkable
class DatasetLoader(Protocol):
    """Contrat d'un loader de dataset (DIP — CR archi #4)."""

    def load(self, source_id: str) -> tuple[LintContext, tuple[LintIssue, ...]]:
        """Renvoie le contexte chargé + d'éventuels issues IO synthétiques."""
        ...


def _load_jsons_with_errors(
    directory: Path, *, source_id: str,
) -> tuple[tuple[dict[str, Any], ...], tuple[LintIssue, ...]]:
    """Charge tous les ``*.json`` d'un dossier.

    Retourne (payloads_valides, issues_io). H7 : chaque fichier skippé
    est loggé sur stderr ET émet un ``LintIssue`` ``rule="dataset_io"``
    pour qu'il soit visible dans le rapport.
    """
    if not directory.exists():
        return (), ()
    payloads: list[dict[str, Any]] = []
    issues: list[LintIssue] = []
    for path in sorted(directory.glob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
            payload = json.loads(text)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            sys.stderr.write(
                f"[lint] dataset_io: fichier illisible "
                f"{path} ({type(exc).__name__}: {exc})\n"
            )
            issues.append(LintIssue(
                rule="dataset_io", severity=Severity.WARNING,
                entity_type="dataset", entity_id=str(path.name),
                field=None,
                message=(
                    f"fichier illisible ({type(exc).__name__}) : "
                    f"{path} (skippé)"
                ),
            ))
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
        else:
            sys.stderr.write(
                f"[lint] dataset_io: payload non-dict "
                f"{path} ({type(payload).__name__})\n"
            )
            issues.append(LintIssue(
                rule="dataset_io", severity=Severity.WARNING,
                entity_type="dataset", entity_id=str(path.name),
                field=None,
                message=(
                    f"payload non-dict ({type(payload).__name__}) : "
                    f"{path} (skippé)"
                ),
            ))
    return tuple(payloads), tuple(issues)


class JsonDatasetLoader:
    """Loader JSON-on-disk concret.

    Composition racine — c'est le CLI qui sait où sont les fichiers.
    Le service ne dépend que du Protocol ``DatasetLoader``.
    """

    def __init__(
        self,
        *,
        recos_base: Path,
        episodes_base: Path,
        items_base: Path,
        mentions_base: Path,
        source_registry_get,  # callable[(str), SourceConfig | None]
        item_repo_factory,    # callable[(Path, str), ItemRepoJson]
        mention_repo_factory,  # callable[(Path, str), MentionRepoJson]
    ) -> None:
        self._recos_base = recos_base
        self._episodes_base = episodes_base
        self._items_base = items_base
        self._mentions_base = mentions_base
        self._registry_get = source_registry_get
        self._item_repo_factory = item_repo_factory
        self._mention_repo_factory = mention_repo_factory

    def load(
        self, source_id: str,
    ) -> tuple[LintContext, tuple[LintIssue, ...]]:
        recos, io1 = _load_jsons_with_errors(
            self._recos_base / source_id, source_id=source_id,
        )
        episodes, io2 = _load_jsons_with_errors(
            self._episodes_base / source_id, source_id=source_id,
        )
        items_repo = self._item_repo_factory(self._items_base, source_id)
        mentions_repo = self._mention_repo_factory(self._mentions_base, source_id)
        items = tuple(items_repo.iter_all())
        mentions = tuple(mentions_repo.iter_all())
        try:
            cfg = self._registry_get(source_id)
        except Exception:
            cfg = None
        ctx = LintContext(
            source_id=source_id,
            recos=recos,
            items=items,
            mentions=mentions,
            episodes=episodes,
            source_config=cfg,
        )
        return ctx, io1 + io2


__all__ = [
    "DatasetLoader",
    "JsonDatasetLoader",
    "_load_jsons_with_errors",
]
