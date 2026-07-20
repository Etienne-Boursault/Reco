"""Adapter : ``tools.domain._legacy.Reco`` → ``ExtractedReco``.

Découple le harness d'évaluation du modèle legacy. Implémente le
Protocol ``ExtractionSource``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

from tools.eval.types import ExtractedReco, ExtractionSource

__all__ = ["LegacyRecoExtractionSource", "legacy_recos_to_extracted"]


def legacy_recos_to_extracted(
    recos: Iterable[object],
) -> list[ExtractedReco]:
    """Convertit une suite de ``Reco`` legacy en ``ExtractedReco``.

    Tolère canard-typage : tout objet exposant ``title`` (et
    optionnellement ``creator`` / ``timestamp``) est accepté.
    """
    out: list[ExtractedReco] = []
    for r in recos:
        title = getattr(r, "title", None)
        if not title:
            continue
        out.append(ExtractedReco(
            title=str(title),
            creator=getattr(r, "creator", None),
            timestamp=getattr(r, "timestamp", None),
        ))
    return out


@dataclass(frozen=True, slots=True)
class LegacyRecoExtractionSource:
    """``ExtractionSource`` basée sur des ``Reco`` legacy.

    Construit l'index ``{episode_guid: tuple[ExtractedReco, ...]}`` à la
    construction. Adapter pur, sans IO.
    """

    by_guid: dict[str, tuple[ExtractedReco, ...]]

    @classmethod
    def from_legacy(
        cls, recos: Sequence[object],
    ) -> "LegacyRecoExtractionSource":
        grouped: dict[str, list[ExtractedReco]] = defaultdict(list)
        for r in recos:
            guid = getattr(r, "episode_guid", None)
            if not guid:
                continue
            title = getattr(r, "title", None)
            if not title:
                continue
            grouped[str(guid)].append(ExtractedReco(
                title=str(title),
                creator=getattr(r, "creator", None),
                timestamp=getattr(r, "timestamp", None),
            ))
        return cls(by_guid={g: tuple(v) for g, v in grouped.items()})

    def for_episode(self, episode_guid: str) -> Iterable[ExtractedReco]:
        return self.by_guid.get(episode_guid, ())

    def episode_guids(self) -> Iterable[str]:
        return tuple(sorted(self.by_guid.keys()))


# Vérif statique : le dataclass implémente bien le Protocol.
_: ExtractionSource = LegacyRecoExtractionSource(by_guid={})
