"""DÉPRÉCIÉ — voir ``intro_text_similarity.py`` (CR archi #8).

Le nom historique ``intro_embedding_check`` était trompeur (aucun
embedding utilisé en Phase 1). Conservé comme alias rétrocompat pour
ne pas casser les imports historiques.

Le nom ``intro_embedding_check`` est RÉSERVÉ à la Phase 2 (vraie
implémentation embedding sémantique — cf. ADR 0013).
"""
from __future__ import annotations

from tools.match_audit.intro_text_similarity import (
    IntroTextSimilarityCheck,
    check_intro_similarity,
)

__all__ = ["IntroTextSimilarityCheck", "check_intro_similarity"]
