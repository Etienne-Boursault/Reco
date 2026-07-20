"""``EvalHarness`` — orchestre la comparaison golden ↔ extraction.

Architecture (cf. ADR 0011) :

  1. Le harness ne fait **pas** d'appel LLM : il consomme un
     ``ExtractionSource`` (Protocol) qui fournit des ``ExtractedReco``.
  2. Pour chaque épisode du golden set, le pairing expected ↔ extracted
     est optimal (Hungarian, cf. ``tools/eval/assignment.py``).
  3. Verdicts (cf. ADR 0011) :
     - score = 1.0 + ts ok → ``EXACT_MATCH`` (TP)
     - score ≥ seuil + ts ok → ``FUZZY_MATCH`` (TP)
     - score ≥ seuil + ts ko → ``WRONG_TIMESTAMP`` (bucket séparé)
     - aucune correspondance → ``MISSED`` (FN)
     - extracted non appariée → ``SPURIOUS`` (FP)
  4. Agrège ``precision``, ``recall``, ``f1``.

``WRONG_TIMESTAMP`` ne compte ni en TP ni en FN/FP (cf. ADR 0011, C1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from tools.common import log
from tools.eval.assignment import linear_sum_assignment
from tools.eval.fuzzy_match import fuzzy_match_score
from tools.eval.golden_set import ExpectedReco, GoldenEpisode, GoldenSet
from tools.eval.metrics import EvalResult, MatchVerdict, f1, precision, recall
from tools.eval.types import (
    EvalConfig,
    EvalDetail,
    EvalMetrics,
    ExtractedReco,
    ExtractionSource,
)

__all__ = ["EvalHarness", "DictExtractionSource"]


def _parse_timestamp_to_seconds(ts: str | None) -> int | None:
    """Convertit ``HH:MM:SS`` ou ``MM:SS`` (ou ``SS``) en secondes.

    Normalise tout vers HH:MM:SS implicitement. ``None`` si invalide.
    """
    if not ts:
        return None
    parts = ts.strip().split(":")
    try:
        ints = [int(p) for p in parts]
    except ValueError:
        return None
    if len(ints) == 3:
        h, m, s = ints
    elif len(ints) == 2:
        h, m, s = 0, ints[0], ints[1]
    elif len(ints) == 1:
        h, m, s = 0, 0, ints[0]
    else:
        return None
    return h * 3600 + m * 60 + s


# --- Source d'extractions par défaut : dict ``{guid: [dict, ...]}`` --------
@dataclass(frozen=True, slots=True)
class DictExtractionSource:
    """Implémente ``ExtractionSource`` à partir d'un mapping legacy
    ``{episode_guid: [dict, ...]}`` ou d'une liste plate."""

    by_guid: Mapping[str, tuple[ExtractedReco, ...]]

    @classmethod
    def from_legacy_dict(
        cls, raw: Mapping[str, Any] | list[Any],
        *, default_guid: str | None = None,
    ) -> "DictExtractionSource":
        by_guid: dict[str, tuple[ExtractedReco, ...]] = {}
        if isinstance(raw, list):
            recos = tuple(_to_extracted(r) for r in raw)
            if default_guid is not None:
                by_guid[default_guid] = recos
            else:
                by_guid["__flat__"] = recos
        else:
            for guid, lst in raw.items():
                if isinstance(lst, list):
                    by_guid[str(guid)] = tuple(_to_extracted(r) for r in lst)
        return cls(by_guid=by_guid)

    def for_episode(self, episode_guid: str) -> Iterable[ExtractedReco]:
        return self.by_guid.get(episode_guid, ())

    def episode_guids(self) -> Iterable[str]:
        return tuple(sorted(self.by_guid.keys()))


def _to_extracted(item: Any) -> ExtractedReco:
    if isinstance(item, ExtractedReco):
        return item
    if isinstance(item, Mapping):
        return ExtractedReco.from_dict(item)
    raise TypeError(
        f"ExtractedReco: type non supporté ({type(item).__name__}).",
    )


class EvalHarness:
    """Orchestre une évaluation. Stateless par épisode."""

    def __init__(
        self,
        golden_set: GoldenSet,
        fuzzy_threshold: float | None = None,
        *,
        config: EvalConfig | None = None,
        emit_jsonl: bool = False,
    ) -> None:
        if config is not None and fuzzy_threshold is not None:
            raise ValueError(
                "Spécifier soit `config`, soit `fuzzy_threshold`, pas les deux.",
            )
        if config is None:
            if fuzzy_threshold is None:
                config = EvalConfig()
            else:
                if not 0.0 < fuzzy_threshold <= 1.0:
                    raise ValueError("fuzzy_threshold doit être dans ]0, 1].")
                config = EvalConfig(fuzzy_threshold=fuzzy_threshold)
        self._golden_set = golden_set
        self._config = config
        self._fuzzy_threshold = config.fuzzy_threshold  # compat tests
        self._emit_jsonl = emit_jsonl

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------
    def evaluate(
        self,
        extracted_recos: list[Any] | ExtractionSource,
        episode_guid: str | None = None,
    ) -> EvalResult:
        """Évalue une liste de recos extraites (legacy) ou une
        ``ExtractionSource``.

        - Si ``episode_guid`` fourni, ne compare qu'à cet épisode.
        - Sinon, fusionne tous les épisodes du golden set.

        Retourne un ``EvalResult`` (compat legacy : ``details`` est un
        tuple de dicts).
        """
        if isinstance(extracted_recos, list):
            extracted = [_to_extracted(r) for r in extracted_recos]
        else:
            # ExtractionSource — fusion sur les guids du golden set.
            extracted = []
            for ep in self._golden_set:
                extracted.extend(extracted_recos.for_episode(ep.episode_guid))

        if episode_guid is not None:
            ep_obj = self._golden_set.by_guid(episode_guid)
            if ep_obj is None:
                raise KeyError(
                    f"Épisode {episode_guid!r} absent du golden set.",
                )
            expected = list(ep_obj.expected_recos)
        else:
            expected = [
                r for ep in self._golden_set for r in ep.expected_recos
            ]
        return self._compare(expected, extracted, episode_guid=episode_guid)

    def evaluate_full(
        self, source: ExtractionSource,
    ) -> EvalMetrics:
        """Évalue tous les épisodes du golden set via ``source``.

        Retourne un ``EvalMetrics`` enrichi de ``per_episode``.
        """
        per_ep: dict[str, EvalMetrics] = {}
        all_expected: list[ExpectedReco] = []
        all_extracted: list[ExtractedReco] = []
        for ep in self._golden_set:
            ep_extracted = list(source.for_episode(ep.episode_guid))
            ep_result = self._compare(
                list(ep.expected_recos), ep_extracted,
                episode_guid=ep.episode_guid,
            )
            per_ep[ep.episode_guid] = _result_to_metrics(ep_result)
            all_expected.extend(ep.expected_recos)
            all_extracted.extend(ep_extracted)

        # Agrégat global.
        global_result = self._compare(all_expected, all_extracted)
        global_metrics = _result_to_metrics(global_result, per_episode=per_ep)
        return global_metrics

    # ------------------------------------------------------------------
    # Cœur de l'algorithme
    # ------------------------------------------------------------------
    def _compare(
        self,
        expected: list[ExpectedReco],
        extracted: list[ExtractedReco],
        *,
        episode_guid: str | None = None,
    ) -> EvalResult:
        details_objs: list[EvalDetail] = []
        n_exact = n_fuzzy = n_missed = n_wrong_ts = 0

        n_exp = len(expected)
        n_ext = len(extracted)

        # Matrice de score (maximize). Fallback sur 0 si l'un des cotés vide.
        assignments: list[tuple[int, int, float]] = []
        if n_exp and n_ext:
            scores = [
                [
                    fuzzy_match_score(
                        exp.title, exp.creator,
                        ex.title, ex.creator,
                        config=self._config,
                    )
                    for ex in extracted
                ]
                for exp in expected
            ]
            row_ind, col_ind = linear_sum_assignment(scores, maximize=True)
            for r, c in zip(row_ind, col_ind, strict=True):
                assignments.append((r, c, scores[r][c]))
        else:
            scores = []

        matched_expected: set[int] = set()
        matched_extracted: set[int] = set()

        for r, c, score in assignments:
            exp = expected[r]
            ex = extracted[c]
            if score < self._config.fuzzy_threshold:
                # Pas un vrai match : on ne consomme pas la paire.
                continue
            matched_expected.add(r)
            matched_extracted.add(c)
            ts_ok = self._timestamp_within_tolerance(exp, ex)
            if not ts_ok:
                verdict = MatchVerdict.WRONG_TIMESTAMP
                n_wrong_ts += 1
            elif score >= 1.0:
                verdict = MatchVerdict.EXACT_MATCH
                n_exact += 1
            else:
                verdict = MatchVerdict.FUZZY_MATCH
                n_fuzzy += 1
            details_objs.append(EvalDetail(
                verdict=verdict.value,
                expected_title=exp.title,
                matched_title=ex.title,
                score=float(score),
                episode_guid=episode_guid,
            ))

        # MISSED = expected non appariées (ordre stable par index).
        for idx, exp in enumerate(expected):
            if idx not in matched_expected:
                # Pour info, score = meilleure similarité disponible (ou 0).
                best_score = 0.0
                if scores:
                    best_score = max(
                        (scores[idx][c] for c in range(n_ext)
                         if c not in matched_extracted),
                        default=0.0,
                    )
                n_missed += 1
                details_objs.append(EvalDetail(
                    verdict=MatchVerdict.MISSED.value,
                    expected_title=exp.title,
                    score=max(best_score, 0.0),
                    episode_guid=episode_guid,
                ))

        # SPURIOUS = extracted non appariées.
        n_spurious = 0
        for idx, ex in enumerate(extracted):
            if idx not in matched_extracted:
                n_spurious += 1
                details_objs.append(EvalDetail(
                    verdict=MatchVerdict.SPURIOUS.value,
                    matched_title=ex.title,
                    episode_guid=episode_guid,
                ))

        n_tp = n_exact + n_fuzzy
        # FP = spurious uniquement (cf. ADR 0011 C1).
        n_fp = n_spurious
        # FN = missed uniquement.
        n_fn = n_missed
        p = precision(n_tp, n_tp + n_fp)
        r = recall(n_tp, n_tp + n_fn)

        # Log JSONL si demandé.
        if self._emit_jsonl:
            log.info(json.dumps({
                "event": "eval.compare",
                "episode_guid": episode_guid,
                "n_expected": n_exp,
                "n_extracted": n_ext,
                "n_exact": n_exact,
                "n_fuzzy": n_fuzzy,
                "n_missed": n_missed,
                "n_spurious": n_spurious,
                "n_wrong_ts": n_wrong_ts,
                "precision": p,
                "recall": r,
                "f1": f1(p, r),
            }, ensure_ascii=False))

        # Tri stable des détails : par episode_guid (None last), puis verdict.
        details_objs.sort(key=lambda d: (
            d.episode_guid or "",
            d.expected_title or d.matched_title or "",
        ))

        details_dicts = tuple(d.to_dict() for d in details_objs)
        return EvalResult(
            n_expected=n_exp,
            n_extracted=n_ext,
            n_exact_match=n_exact,
            n_fuzzy_match=n_fuzzy,
            n_missed=n_missed,
            n_spurious=n_spurious,
            n_wrong_timestamp=n_wrong_ts,
            precision=p,
            recall=r,
            f1=f1(p, r),
            details=details_dicts,
        )

    def _timestamp_within_tolerance(
        self, exp: ExpectedReco, ex: ExtractedReco,
    ) -> bool:
        """Vrai si :
        - aucun timestamp attendu, OU
        - le timestamp extrait est dans ``[exp ± tolerance]``.
        Si timestamp attendu mais non fourni → ``True``.
        """
        if not exp.timestamp:
            return True
        exp_sec = _parse_timestamp_to_seconds(exp.timestamp)
        if exp_sec is None:
            return True
        if ex.timestamp is None:
            return True
        got_sec = _parse_timestamp_to_seconds(str(ex.timestamp))
        if got_sec is None:
            return True
        # Tolérance = la plus large entre celle de l'expected (golden set)
        # et celle du config global.
        tol = max(
            exp.timestamp_tolerance_sec, self._config.timestamp_tolerance_sec,
        )
        return abs(got_sec - exp_sec) <= tol


def _result_to_metrics(
    res: EvalResult,
    *,
    per_episode: Mapping[str, EvalMetrics] | None = None,
) -> EvalMetrics:
    """Convertit ``EvalResult`` (compat dicts) → ``EvalMetrics`` typé."""
    details_typed = tuple(
        EvalDetail(
            verdict=d["verdict"],
            expected_title=d.get("expected_title"),
            matched_title=d.get("matched_title") or d.get("extracted_title"),
            score=d.get("score") if isinstance(d.get("score"), (int, float))
            else None,
            episode_guid=d.get("episode_guid"),
        )
        for d in res.details
    )
    return EvalMetrics(
        n_expected=res.n_expected,
        n_extracted=res.n_extracted,
        n_exact_match=res.n_exact_match,
        n_fuzzy_match=res.n_fuzzy_match,
        n_missed=res.n_missed,
        n_spurious=res.n_spurious,
        n_wrong_timestamp=res.n_wrong_timestamp,
        precision=res.precision,
        recall=res.recall,
        f1=res.f1,
        details=details_typed,
        per_episode=per_episode or {},
    )
