"""Check : similarité titre RSS Acast ↔ titre YouTube.

Signal **complémentaire** (severity=warning par défaut) : la chaîne
``@KyanKhojandi`` publie sous des titres de format (« A Good Time with X »)
qui font chuter le score de similarité alors que le match est correct.
Donc un score bas n'est pas une preuve solide — on émet juste un warning,
visible dans le rapport mais qui NE déclenche PAS ``matchSuspect``.

Cf. mémoire projet ``reco-yt-format-titles``.

Note (CR archi #22) : la similarité de titre est réimplémentée localement
(``difflib.SequenceMatcher`` sur normalize_text). ``tools/match_youtube.py``
expose seulement ``_similarity`` privé — refacto vers une API publique
``title_match_score`` partagée est REPORTÉ Sprint 3 (zone hors scope P1.6).
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Mapping

from common import normalize_text  # type: ignore[attr-defined]

from tools.match_audit.protocols import EpisodeView
from tools.match_audit.settings import DEFAULT_TITLE_THRESHOLD
from tools.match_audit.types import MatchSuspicion, Severity


def _coerce(ep: EpisodeView | Mapping[str, Any]) -> EpisodeView | None:
    if isinstance(ep, EpisodeView):
        return ep
    if isinstance(ep, Mapping):
        return EpisodeView.from_dict({**ep, "guid": ep.get("guid") or "_anonymous_"})
    return None  # pragma: no cover — defensive


def check_title_similarity(
    ep: EpisodeView | Mapping[str, Any],
    threshold: float = DEFAULT_TITLE_THRESHOLD,
) -> MatchSuspicion | None:
    """Retourne un ``MatchSuspicion`` (severity=warning) si titre RSS et YT divergent.

    Severity ``warning`` par DEFAUT (cf. ``KyanKhojandi`` format titles).
    """
    view = _coerce(ep)
    if view is None:
        return None  # pragma: no cover — defensive
    if not view.title or not view.youtube_title:
        return None
    a = normalize_text(view.title)
    b = normalize_text(view.youtube_title)
    if not a or not b:
        return None
    ratio = SequenceMatcher(a=a, b=b).ratio()
    if ratio >= threshold:
        return None
    return MatchSuspicion(
        kind="title_drift",
        detail=f"title similarity {ratio:.2f} < {threshold}",
        severity=Severity.WARNING,
    )


@dataclass(frozen=True, slots=True)
class TitleSimilarityCheck:
    threshold: float = DEFAULT_TITLE_THRESHOLD
    kind: str = "title_drift"
    severity: Severity = Severity.WARNING
    description: str = (
        "Re-mesure similarité titre RSS↔YT (signal warning, ne flag pas)."
    )

    def check(self, ep: EpisodeView) -> MatchSuspicion | None:
        return check_title_similarity(ep, self.threshold)


__all__ = ["TitleSimilarityCheck", "check_title_similarity"]
