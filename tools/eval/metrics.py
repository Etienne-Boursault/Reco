"""Métriques d'évaluation : precision, recall, F1 + classification verdict.

Fonctions pures, sans dépendance vers le reste du projet — permettent un
test ciblé et une réutilisation depuis n'importe quel reporter.

## Sémantique des verdicts (cf. ADR 0011)

- ``EXACT_MATCH`` : score = 1.0 ET timestamp dans la tolérance. Compte
  comme True Positive (TP).
- ``FUZZY_MATCH`` : score ∈ [seuil, 1[ ET timestamp ok. TP.
- ``WRONG_TIMESTAMP`` : score ≥ seuil mais timestamp hors tolérance.
  **Ni TP, ni FP, ni FN** — bucket séparé (cf. C1). On expose néanmoins
  une variante ``precision/recall`` où il compte comme TP pondéré
  (``f1_inclusive_ts``) à des fins de débogage.
- ``MISSED`` / ``MISSING_GOLD`` : pas d'extraction au-dessus du seuil
  pour cette reco golden → False Negative (FN).
- ``SPURIOUS`` / ``EXTRA_PREDICTED`` : extraction sans expected
  correspondant → False Positive (FP).

``MISSED`` et ``MISSING_GOLD`` sont **synonymes** (compat legacy : on
garde MISSED en sortie par défaut). Idem ``SPURIOUS``/``EXTRA_PREDICTED``.

Formules :
    precision = TP / (TP + FP)
    recall    = TP / (TP + FN)
    f1        = 2·P·R / (P + R)

Avec :
    TP = n_exact_match + n_fuzzy_match
    FP = n_spurious
    FN = n_missed
    (n_wrong_timestamp est hors compte — voir ADR 0011)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from tools.eval.types import EvalDetail, EvalMetrics

__all__ = [
    "EvalResult",
    "EvalMetrics",
    "MatchVerdict",
    "f1",
    "f1_inclusive_ts",
    "precision",
    "recall",
]


class MatchVerdict(StrEnum):
    """Verdict de classification d'une reco lors d'une comparaison."""

    EXACT_MATCH = "exact"
    FUZZY_MATCH = "fuzzy"
    MISSED = "missed"              # alias historique de MISSING_GOLD
    MISSING_GOLD = "missing_gold"  # FN explicite (cf. H1)
    SPURIOUS = "spurious"          # alias historique d'EXTRA_PREDICTED
    EXTRA_PREDICTED = "extra"      # FP explicite (cf. H1)
    WRONG_TIMESTAMP = "wrong_ts"


# Verdicts comptés comme True Positive.
_TP_VERDICTS: Final[frozenset[str]] = frozenset({
    MatchVerdict.EXACT_MATCH.value,
    MatchVerdict.FUZZY_MATCH.value,
})


def precision(n_true_positive: int, n_extracted: int) -> float:
    """Precision = TP / total extraits. Retourne ``0.0`` si dénominateur nul."""
    if n_extracted <= 0:
        return 0.0
    return n_true_positive / n_extracted


def recall(n_true_positive: int, n_expected: int) -> float:
    """Recall = TP / total attendus. Retourne ``0.0`` si dénominateur nul."""
    if n_expected <= 0:
        return 0.0
    return n_true_positive / n_expected


def f1(p: float, r: float) -> float:
    """F1 = moyenne harmonique de precision/recall. ``0.0`` si l'un est nul."""
    if p <= 0.0 or r <= 0.0:
        return 0.0
    return 2.0 * p * r / (p + r)


def f1_inclusive_ts(
    n_exact: int,
    n_fuzzy: int,
    n_wrong_ts: int,
    n_missed: int,
    n_spurious: int,
) -> float:
    """F1 alternatif comptant ``WRONG_TIMESTAMP`` comme TP pondéré (×0.5).

    Utile pour débugger un pipeline qui hallucine systématiquement les
    timestamps mais identifie correctement les titres. Cf. ADR 0011.
    """
    tp_weighted = n_exact + n_fuzzy + 0.5 * n_wrong_ts
    extracted = n_exact + n_fuzzy + n_wrong_ts + n_spurious
    expected = n_exact + n_fuzzy + n_wrong_ts + n_missed
    p = tp_weighted / extracted if extracted else 0.0
    r = tp_weighted / expected if expected else 0.0
    return f1(p, r)


# --- Compat legacy : EvalResult = EvalMetrics + champ ``details`` en dict --
# Les tests historiques (`test_metrics.py`, `test_reporters.py`) instancient
# ``EvalResult(...)`` avec ``details=(<dict>, ...)``. On garde une dataclass
# distincte qui accepte ces dicts bruts tout en permettant l'évolution vers
# ``EvalDetail`` côté harness.
@dataclass(frozen=True, slots=True)
class EvalResult:
    """Résultat agrégé (compat legacy). Préférer ``EvalMetrics`` pour le
    nouveau code."""

    n_expected: int
    n_extracted: int
    n_exact_match: int
    n_fuzzy_match: int
    n_missed: int
    n_spurious: int
    n_wrong_timestamp: int
    precision: float
    recall: float
    f1: float
    details: tuple = field(default_factory=tuple)


def _tp_count_from_details(details: tuple[EvalDetail, ...]) -> int:
    return sum(1 for d in details if d.verdict in _TP_VERDICTS)
