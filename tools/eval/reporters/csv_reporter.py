"""CSV reporter — export d'un ``EvalResult``/``EvalMetrics`` au format CSV.

Conformément à la CR senior (M3) :
- ``csv.DictWriter`` avec ``quoting=QUOTE_MINIMAL``, virgule, UTF-8 BOM.
- Section "summary" (1 ligne) puis section "details" (N lignes).
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Mapping

from tools.eval.metrics import EvalResult
from tools.eval.reporters.base import register_reporter
from tools.eval.types import EvalMetrics

__all__ = [
    "CsvReporter",
    "render_csv",
    "write_csv",
]


_SUMMARY_FIELDS = (
    "n_expected",
    "n_extracted",
    "n_exact_match",
    "n_fuzzy_match",
    "n_missed",
    "n_spurious",
    "n_wrong_timestamp",
    "precision",
    "recall",
    "f1",
)

_DETAIL_FIELDS = ("verdict", "expected_title", "matched_title", "score",
                  "episode_guid")


def _details_iter(result: Any) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for d in result.details:
        if hasattr(d, "to_dict"):
            out.append(d.to_dict())
        else:
            out.append(d)
    return out


def render_csv(result: EvalResult | EvalMetrics) -> str:
    """Sérialise ``result`` en CSV (string)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["# summary"])
    writer.writerow(_SUMMARY_FIELDS)
    writer.writerow([getattr(result, k) for k in _SUMMARY_FIELDS])
    writer.writerow([])
    writer.writerow(["# details"])
    dict_writer = csv.DictWriter(
        buf, fieldnames=_DETAIL_FIELDS, lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL, extrasaction="ignore",
    )
    dict_writer.writeheader()
    for d in _details_iter(result):
        row = {k: d.get(k, "") for k in _DETAIL_FIELDS}
        # Compat legacy : ``extracted_title`` → ``matched_title``.
        if not row["matched_title"] and "extracted_title" in d:
            row["matched_title"] = d["extracted_title"]
        dict_writer.writerow(row)
    return buf.getvalue()


def write_csv(result: EvalResult | EvalMetrics, path: str | Path) -> Path:
    """Écrit le CSV (UTF-8 BOM, Excel-friendly) à ``path``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_csv(result), encoding="utf-8-sig")
    return p


@register_reporter("csv")
class CsvReporter:
    """Reporter CSV (implémente le Protocol ``EvalReporter``)."""

    def render(
        self, metrics: EvalResult | EvalMetrics, *, title: str = "",
    ) -> str:
        _ = title  # CSV n'a pas de titre
        return render_csv(metrics)

    def write(
        self, metrics: EvalResult | EvalMetrics, path: str | Path,
        *, title: str = "",
    ) -> Path:
        _ = title
        return write_csv(metrics, path)
