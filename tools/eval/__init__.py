"""Harness d'évaluation : golden set + métriques precision/recall/F1.

Voir ADR 0011 (``docs/adr/0011-eval-harness.md``) pour la stratégie globale.
"""
from __future__ import annotations

from tools.eval.fuzzy_match import fuzzy_match_score, normalize_text
from tools.eval.golden_set import (
    ExpectedReco,
    GoldenEpisode,
    GoldenSet,
    GoldenSetError,
    golden_set_hash,
    load_golden_set,
)
from tools.eval.harness import DictExtractionSource, EvalHarness
from tools.eval.metrics import EvalResult, MatchVerdict, f1, precision, recall
from tools.eval.types import (
    EvalConfig,
    EvalDetail,
    EvalMetrics,
    EvalReporter,
    ExtractedReco,
    ExtractionSource,
    ReportFormat,
    RunManifest,
)

__all__ = [
    "DictExtractionSource",
    "EvalConfig",
    "EvalDetail",
    "EvalHarness",
    "EvalMetrics",
    "EvalReporter",
    "EvalResult",
    "ExpectedReco",
    "ExtractedReco",
    "ExtractionSource",
    "GoldenEpisode",
    "GoldenSet",
    "GoldenSetError",
    "MatchVerdict",
    "ReportFormat",
    "RunManifest",
    "f1",
    "fuzzy_match_score",
    "golden_set_hash",
    "load_golden_set",
    "normalize_text",
    "precision",
    "recall",
]
