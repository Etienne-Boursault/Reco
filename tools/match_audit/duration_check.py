"""Check : durée Acast vs YouTube.

Si l'écart relatif dépasse ``tolerance`` (défaut 5%), on flag — c'est le
signal le plus fiable d'un mauvais match (un audio de 1h vs une vidéo de
1h30 ≠ même contenu).

Le check est exposé sous DEUX formes complémentaires :

- ``check_duration(ep_dict_or_view, tolerance)`` — fonction rétrocompatible
  pour les tests historiques qui passent un ``dict`` brut.
- ``DurationCheck(tolerance)`` — classe immuable conforme au Protocol
  ``MatchCheck`` (CR archi #2), consommée par ``MatchAuditService``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from tools.match_audit.protocols import EpisodeView
from tools.match_audit.settings import DEFAULT_DURATION_TOLERANCE
from tools.match_audit.types import MatchSuspicion, Severity


def _coerce(ep: EpisodeView | Mapping[str, Any]) -> EpisodeView | None:
    if isinstance(ep, EpisodeView):
        return ep
    if isinstance(ep, Mapping):
        return EpisodeView.from_dict({**ep, "guid": ep.get("guid") or "_anonymous_"})
    return None


def check_duration(
    ep: EpisodeView | Mapping[str, Any],
    tolerance: float = DEFAULT_DURATION_TOLERANCE,
) -> MatchSuspicion | None:
    """Retourne une ``MatchSuspicion`` si les durées divergent au-delà de ``tolerance``.

    None si :
      - une des deux durées est absente (impossible de juger),
      - ``audioDuration`` vaut 0 (garde-fou division par zéro).
    """
    view = _coerce(ep)
    if view is None:
        return None
    audio = view.audio_duration
    yt = view.youtube_duration
    if audio is None or yt is None:
        return None
    if audio <= 0:
        return None
    diff_ratio = abs(audio - yt) / audio
    if diff_ratio <= tolerance:
        return None
    return MatchSuspicion(
        kind="duration_mismatch",
        detail=f"Acast={audio}s vs YT={yt}s (diff {diff_ratio:.1%})",
        severity=Severity.ERROR,
    )


@dataclass(frozen=True, slots=True)
class DurationCheck:
    """Adaptateur Protocol ``MatchCheck``."""

    tolerance: float = DEFAULT_DURATION_TOLERANCE
    kind: str = "duration_mismatch"
    severity: Severity = Severity.ERROR
    description: str = (
        "Compare audioDuration (Acast) et youtubeDuration (YT). "
        "Flag si écart relatif > tolerance."
    )

    def check(self, ep: EpisodeView) -> MatchSuspicion | None:
        return check_duration(ep, self.tolerance)


__all__ = ["DurationCheck", "check_duration"]
