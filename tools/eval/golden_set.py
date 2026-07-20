"""Charge et valide les golden sets d'évaluation.

Un golden set = répertoire contenant N fichiers ``*.json`` décrivant
chacun un épisode annoté manuellement avec les recos attendues. Voir
``docs/adr/0011-eval-harness.md`` pour le schéma complet.

Le schéma est volontairement minimaliste et immuable (dataclasses
``frozen=True, slots=True``).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

__all__ = [
    "ExpectedReco",
    "GoldenEpisode",
    "GoldenSet",
    "GoldenSetError",
    "golden_set_hash",
    "load_golden_set",
]


class GoldenSetError(ValueError):
    """Levée si le golden set est invalide (schéma cassé, fichier illisible)."""


@dataclass(frozen=True, slots=True)
class ExpectedReco:
    """Une reco attendue dans un épisode golden.

    Invariant : ``title`` non-vide. ``timestamp`` accepte ``HH:MM:SS``
    ou ``MM:SS`` (parsé par le harness).
    """

    title: str
    creator: str | None = None
    types: tuple[str, ...] = ()
    timestamp: str | None = None
    timestamp_tolerance_sec: int = 30
    recommended_by: str | None = None
    kind: str = "reco"
    must_have: bool = True
    notes: str = ""

    @classmethod
    def from_dict(
        cls, data: Mapping[str, object], *, context: str = "",
    ) -> "ExpectedReco":
        """Construit un ``ExpectedReco`` depuis un mapping JSON.

        ``context`` est ajouté aux messages d'erreur (ex : ``"ep001.json [3]"``).
        """
        prefix = f"{context}: " if context else ""
        if "title" not in data or not str(data["title"]).strip():
            raise GoldenSetError(
                f"{prefix}ExpectedReco: champ `title` manquant ou vide.",
            )
        types_raw = data.get("types") or ()
        if not isinstance(types_raw, (list, tuple)):
            raise GoldenSetError(
                f"{prefix}ExpectedReco: `types` doit être une liste de strings.",
            )
        return cls(
            title=str(data["title"]),
            creator=data.get("creator"),  # type: ignore[arg-type]
            types=tuple(str(t) for t in types_raw),
            timestamp=data.get("timestamp"),  # type: ignore[arg-type]
            timestamp_tolerance_sec=int(data.get("timestamp_tolerance_sec", 30)),
            recommended_by=data.get("recommended_by"),  # type: ignore[arg-type]
            kind=str(data.get("kind", "reco")),
            must_have=bool(data.get("must_have", True)),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True, slots=True)
class GoldenEpisode:
    """Un épisode annoté.

    Invariant : ``episode_guid`` et ``source_id`` non-vides ;
    ``expected_recos`` est un tuple (immuable).
    """

    episode_guid: str
    source_id: str
    expected_recos: tuple[ExpectedReco, ...]
    annotator: str = ""
    annotated_at: str = ""

    @classmethod
    def from_dict(
        cls, data: Mapping[str, object], *, context: str = "",
    ) -> "GoldenEpisode":
        prefix = f"{context}: " if context else ""
        guid = data.get("episode_guid")
        sid = data.get("source_id")
        if not guid or not sid:
            raise GoldenSetError(
                f"{prefix}GoldenEpisode: `episode_guid` et `source_id` requis.",
            )
        recos_raw = data.get("expected_recos")
        if not isinstance(recos_raw, list):
            raise GoldenSetError(
                f"{prefix}GoldenEpisode: `expected_recos` doit être une liste.",
            )
        recos = tuple(
            ExpectedReco.from_dict(r, context=f"{context}[reco#{i}]")
            for i, r in enumerate(recos_raw)
        )
        return cls(
            episode_guid=str(guid),
            source_id=str(sid),
            expected_recos=recos,
            annotator=str(data.get("annotator", "")),
            annotated_at=str(data.get("annotated_at", "")),
        )


@dataclass(frozen=True, slots=True)
class GoldenSet:
    """Collection d'épisodes annotés (immuable)."""

    episodes: tuple[GoldenEpisode, ...] = field(default_factory=tuple)

    def __iter__(self) -> Iterable[GoldenEpisode]:  # type: ignore[override]
        return iter(self.episodes)

    def __len__(self) -> int:
        return len(self.episodes)

    def by_guid(self, guid: str) -> GoldenEpisode | None:
        for ep in self.episodes:
            if ep.episode_guid == guid:
                return ep
        return None

    def by_source(self, source_id: str) -> "GoldenSet":
        """Filtre les épisodes par ``source_id``."""
        return GoldenSet(episodes=tuple(
            e for e in self.episodes if e.source_id == source_id
        ))


def load_golden_set(path: str | Path) -> GoldenSet:
    """Charge tous les ``*.json`` d'un dossier (non récursif) ou un seul fichier.

    Lève ``GoldenSetError`` si le chemin n'existe pas ou si un fichier est
    invalide (message inclut le nom du fichier).
    """
    p = Path(path)
    if not p.exists():
        raise GoldenSetError(f"Golden set introuvable : {p}")
    files = [p] if p.is_file() else sorted(p.glob("*.json"))
    episodes: list[GoldenEpisode] = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GoldenSetError(f"Impossible de lire {f}: {exc}") from exc
        if not isinstance(data, dict):
            raise GoldenSetError(
                f"{f.name}: racine doit être un objet JSON.",
            )
        episodes.append(GoldenEpisode.from_dict(data, context=f.name))
    return GoldenSet(episodes=tuple(episodes))


def golden_set_hash(golden_set: GoldenSet) -> str:
    """Hash SHA-256 stable d'un golden set (pour run manifest)."""
    h = hashlib.sha256()
    for ep in sorted(golden_set, key=lambda e: e.episode_guid):
        h.update(ep.episode_guid.encode("utf-8"))
        h.update(b"|")
        h.update(ep.source_id.encode("utf-8"))
        for r in ep.expected_recos:
            h.update(b"||")
            h.update(r.title.encode("utf-8"))
            h.update(b"|")
            h.update((r.creator or "").encode("utf-8"))
            h.update(b"|")
            h.update((r.timestamp or "").encode("utf-8"))
    return h.hexdigest()
