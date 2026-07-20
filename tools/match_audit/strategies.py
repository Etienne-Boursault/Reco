"""Stratégies pluggables — pattern Strategy.

Pour l'instant, une seule stratégie d'``IntroSimilarityStrategy`` est
implémentée (``SequenceMatcherStrategy``). Le Protocol existe pour
permettre une bascule en Phase 2 sur ``EmbeddingStrategy``
(sentence-transformers / OpenAI embeddings — cf. ADR 0013).
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True, slots=True)
class SequenceMatcherStrategy:
    """Similarité texte basée sur ``difflib.SequenceMatcher``.

    Aucune dépendance externe — fonctionne offline. Recommandée par défaut
    pour le check intro (cf. ADR 0013).
    """

    def compare(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return SequenceMatcher(a=a, b=b).ratio()


__all__ = ["SequenceMatcherStrategy"]
