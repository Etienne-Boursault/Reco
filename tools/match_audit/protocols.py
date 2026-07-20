"""Protocols (DIP) — découplent le service des dépendances I/O.

- ``EpisodeView`` : projection figée d'un épisode pour les checks
  (au lieu de balancer un ``dict`` brut dans toute la pile).
- ``TranscriptRepo`` : un seul Protocol pour les deux providers
  (Acast/YouTube) — élimine le fallback ambigu sur ``<guid>.txt``
  (CR senior C3, CR archi #10).
- ``EpisodeRepo`` : abstrait la lecture/écriture des JSON d'épisodes
  (DIP — le ``flag_writer`` ne dépend plus de ``common.*`` direct).
- ``AuditTrail`` : journal append-only pour --apply (CR archi #11, #6).
- ``MatchCheck`` : Protocol de check (CR archi #2).
- ``IntroSimilarityStrategy`` : Strategy pour le calcul de similarité
  intro (CR archi #9 — prépare l'embedding Phase 2 sans l'implémenter).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

from tools.match_audit.types import MatchSuspicion, Severity

TranscriptKind = Literal["acast", "youtube"]


@dataclass(frozen=True, slots=True)
class EpisodeView:
    """Projection IMMUABLE d'un épisode JSON pour la chaîne de checks.

    Garantit que les checks reçoivent un objet bien formé (guid non vide)
    et qu'ils ne peuvent muter le payload (frozen=True).

    Le champ ``raw`` expose le dict d'origine pour les checks qui auraient
    besoin de champs non typés (compromis pragmatique : on évolue vers une
    structure pleinement typée au fur et à mesure).
    """

    guid: str
    title: str | None
    youtube_title: str | None
    audio_duration: int | None
    youtube_duration: int | None
    raw: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.guid, str) or not self.guid:
            raise ValueError("EpisodeView.guid doit être une str non vide")

    @classmethod
    def from_dict(cls, ep: Mapping[str, Any]) -> "EpisodeView | None":
        """Construit une vue depuis un dict JSON brut. ``None`` si guid absent."""
        guid = ep.get("guid")
        if not isinstance(guid, str) or not guid:
            return None
        return cls(
            guid=guid,
            title=ep.get("title") if isinstance(ep.get("title"), str) else None,
            youtube_title=(
                ep.get("youtubeTitle")
                if isinstance(ep.get("youtubeTitle"), str)
                else None
            ),
            audio_duration=ep.get("audioDuration") if isinstance(
                ep.get("audioDuration"), int,
            ) and not isinstance(ep.get("audioDuration"), bool) else None,
            youtube_duration=ep.get("youtubeDuration") if isinstance(
                ep.get("youtubeDuration"), int,
            ) and not isinstance(ep.get("youtubeDuration"), bool) else None,
            raw=dict(ep),
        )


# ---------------------------------------------------------------------------
# Repos / strategies / trail
# ---------------------------------------------------------------------------


@runtime_checkable
class TranscriptRepo(Protocol):
    """Accès aux transcripts. Une SEULE méthode, paramétrée par ``kind``
    (élimine la duplication ``acast_transcript_provider`` /
    ``yt_transcript_provider`` et le fallback ``.txt`` ambigu — CR C3/#10).
    """

    def get(self, guid: str, kind: TranscriptKind) -> str | None: ...


@runtime_checkable
class EpisodeRepo(Protocol):
    """Persistance d'un épisode JSON (DIP — flag_writer ne dépend plus de
    ``common.*`` direct).
    """

    def load(self, path: Path) -> dict[str, Any]: ...

    def save_if_changed(self, path: Path, data: Mapping[str, Any]) -> bool: ...


@runtime_checkable
class AuditTrail(Protocol):
    """Journal append-only des actions ``--apply`` (CR archi #11, #6).

    Permet aussi le ``--undo-last`` (CR archi #6) en relisant la dernière
    entrée.
    """

    def record(self, event: Mapping[str, Any]) -> None: ...


@runtime_checkable
class MatchCheck(Protocol):
    """Protocol d'un check (CR archi #2).

    - ``kind``        : famille du check.
    - ``severity``    : sévérité par défaut quand il flag.
    - ``description`` : phrase courte (pour --help / rapport).
    - ``check(ep)``   : retourne une suspicion OU ``None``.
    """

    kind: str
    severity: Severity
    description: str

    def check(self, ep: EpisodeView) -> MatchSuspicion | None: ...


@runtime_checkable
class IntroSimilarityStrategy(Protocol):
    """Stratégie de comparaison intro→intro.

    Implémentation par défaut (`SequenceMatcherStrategy`) basée sur
    ``difflib.SequenceMatcher``. Une `EmbeddingStrategy` est prévue pour
    la Phase 2 — voir ADR 0013 et ADR 0015.
    """

    def compare(self, a: str, b: str) -> float: ...


__all__ = [
    "AuditTrail",
    "EpisodeRepo",
    "EpisodeView",
    "IntroSimilarityStrategy",
    "MatchCheck",
    "TranscriptKind",
    "TranscriptRepo",
]
