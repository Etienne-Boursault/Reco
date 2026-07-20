"""Check : similarité textuelle des intros Acast vs YouTube.

(Renommé depuis ``intro_embedding_check.py`` — CR archi #8 : le nom
ancien suggérait à tort une comparaison par embedding sémantique alors
qu'on n'utilise que ``difflib.SequenceMatcher`` en Phase 1. Le nom
``intro_embedding_check`` est RÉSERVÉ pour la Phase 2 — cf. ADR 0013.)

Approche pragmatique :

- on tronque les transcripts aux ``intro_chars`` premiers caractères
  (proxy des ~30 premières secondes) ;
- on mesure une similarité textuelle via la ``IntroSimilarityStrategy``
  injectée (par défaut ``SequenceMatcherStrategy``) ;
- on compare AUSSI une fenêtre milieu (5000-5500) pour mitiger le
  faux-négatif "jingle générique" (CR senior H8) — la similarité retenue
  est le MAX des deux fenêtres (la plus favorable au "même contenu").

Si la similarité tombe sous ``threshold`` (défaut 0.4), c'est suspect :
les deux transcripts ne semblent pas relater le même contenu.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from common import normalize_text  # type: ignore[attr-defined]

from tools.match_audit.protocols import (
    EpisodeView,
    IntroSimilarityStrategy,
    TranscriptKind,
    TranscriptRepo,
)
from tools.match_audit.settings import (
    DEFAULT_INTRO_CHARS,
    DEFAULT_INTRO_THRESHOLD,
)
from tools.match_audit.strategies import SequenceMatcherStrategy
from tools.match_audit.types import MatchSuspicion, Severity

# Fenêtre milieu (5000-5500) pour mitiger le faux-négatif jingle générique
# (CR senior H8). Au-delà de ~5000 chars, on est sortis du pré-générique.
_MID_OFFSET: int = 5000
_MID_WINDOW: int = 500


def _coerce(ep: EpisodeView | Mapping[str, Any]) -> EpisodeView | None:
    if isinstance(ep, EpisodeView):
        return ep
    if isinstance(ep, Mapping):
        return EpisodeView.from_dict({**ep, "guid": ep.get("guid") or "_anonymous_"})
    return None  # pragma: no cover — defensive, type system rejette ce cas


def _window(text: str, start: int, length: int) -> str:
    if start >= len(text):
        return ""
    return text[start:start + length]


def _compare(
    a_text: str,
    y_text: str,
    *,
    intro_chars: int,
    strategy: IntroSimilarityStrategy,
) -> float:
    """Retourne le MAX entre la similarité d'intro et celle de la fenêtre milieu."""
    a_intro = normalize_text(_window(a_text, 0, intro_chars))
    y_intro = normalize_text(_window(y_text, 0, intro_chars))
    score_intro = strategy.compare(a_intro, y_intro) if (a_intro and y_intro) else 0.0

    a_mid = normalize_text(_window(a_text, _MID_OFFSET, _MID_WINDOW))
    y_mid = normalize_text(_window(y_text, _MID_OFFSET, _MID_WINDOW))
    if a_mid and y_mid:
        score_mid = strategy.compare(a_mid, y_mid)
    else:
        score_mid = 0.0
    return max(score_intro, score_mid)


def check_intro_similarity(
    ep: EpisodeView | Mapping[str, Any],
    *,
    acast_transcript_provider: Callable[[str], str | None] | None = None,
    yt_transcript_provider: Callable[[str], str | None] | None = None,
    transcript_repo: TranscriptRepo | None = None,
    threshold: float = DEFAULT_INTRO_THRESHOLD,
    intro_chars: int = DEFAULT_INTRO_CHARS,
    strategy: IntroSimilarityStrategy | None = None,
) -> MatchSuspicion | None:
    """Compare intros Acast vs YouTube et retourne une suspicion si trop éloignées.

    Deux signatures supportées (rétrocompat) :

    - **Nouvelle (recommandée)** : passer ``transcript_repo`` qui résout
      ``(guid, kind)`` (CR archi #10 — un seul Protocol).
    - **Legacy** : passer deux callables ``*_transcript_provider`` (tests
      historiques).

    None si :
      - guid invalide,
      - un des deux transcripts est absent/vide après normalisation.
    """
    view = _coerce(ep)
    if view is None:
        return None  # pragma: no cover — defensive

    if transcript_repo is not None:
        acast = transcript_repo.get(view.guid, "acast") or ""
        yt = transcript_repo.get(view.guid, "youtube") or ""
    else:
        if acast_transcript_provider is None or yt_transcript_provider is None:
            raise ValueError(
                "check_intro_similarity exige soit transcript_repo, "
                "soit les deux providers legacy",
            )
        acast = acast_transcript_provider(view.guid) or ""
        yt = yt_transcript_provider(view.guid) or ""

    if not acast.strip() or not yt.strip():
        return None

    strat = strategy or SequenceMatcherStrategy()
    ratio = _compare(acast, yt, intro_chars=intro_chars, strategy=strat)
    # Si les deux normalize_text donnent vide → on ne juge pas.
    if ratio == 0.0 and not (
        normalize_text(acast[:intro_chars]) and normalize_text(yt[:intro_chars])
    ):
        return None
    if ratio >= threshold:
        return None
    return MatchSuspicion(
        kind="intro_mismatch",
        detail=f"intro similarity {ratio:.2f} < {threshold}",
        severity=Severity.ERROR,
    )


@dataclass(frozen=True, slots=True)
class IntroTextSimilarityCheck:
    """Adaptateur Protocol ``MatchCheck`` pour le check intro."""

    transcript_repo: TranscriptRepo
    threshold: float = DEFAULT_INTRO_THRESHOLD
    intro_chars: int = DEFAULT_INTRO_CHARS
    strategy_factory: Callable[[], IntroSimilarityStrategy] = SequenceMatcherStrategy
    kind: str = "intro_mismatch"
    severity: Severity = Severity.ERROR
    description: str = (
        "Compare les premiers caractères des transcripts Acast/YT "
        "+ une fenêtre milieu (mitige les jingles d'intro génériques)."
    )

    def check(self, ep: EpisodeView) -> MatchSuspicion | None:
        return check_intro_similarity(
            ep,
            transcript_repo=self.transcript_repo,
            threshold=self.threshold,
            intro_chars=self.intro_chars,
            strategy=self.strategy_factory(),
        )


__all__ = [
    "IntroTextSimilarityCheck",
    "check_intro_similarity",
]
