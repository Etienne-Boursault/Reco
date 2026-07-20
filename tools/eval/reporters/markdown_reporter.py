"""Markdown reporter — rapport humain d'un ``EvalResult``/``EvalMetrics``.

Cf. CR senior M8 : table top-5 / bottom-5 épisodes par F1 si ``per_episode``
est exposé (``EvalMetrics``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from tools.eval.metrics import EvalResult
from tools.eval.reporters.base import register_reporter
from tools.eval.types import EvalMetrics

__all__ = ["MarkdownReporter", "render_markdown", "write_markdown"]


def _fmt_pct(x: float) -> str:
    return f"{100.0 * x:.2f}%"


def _details_iter(result: Any) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for d in result.details:
        if hasattr(d, "to_dict"):
            out.append(d.to_dict())
        else:
            out.append(d)
    return out


def _render_summary(result: EvalResult | EvalMetrics) -> list[str]:
    lines = [
        "## Résumé",
        "",
        "| Métrique | Valeur |",
        "|---|---|",
        f"| Precision | {_fmt_pct(result.precision)} |",
        f"| Recall | {_fmt_pct(result.recall)} |",
        f"| F1 | {_fmt_pct(result.f1)} |",
        f"| Attendues | {result.n_expected} |",
        f"| Extraites | {result.n_extracted} |",
        f"| Exact | {result.n_exact_match} |",
        f"| Fuzzy | {result.n_fuzzy_match} |",
        f"| Manquées | {result.n_missed} |",
        f"| Spurious | {result.n_spurious} |",
        f"| Mauvais timestamp | {result.n_wrong_timestamp} |",
        "",
    ]
    return lines


def _render_per_episode_summary(result: EvalMetrics) -> list[str]:
    per_ep = getattr(result, "per_episode", {})
    if not per_ep:
        return []
    ranked = sorted(per_ep.items(), key=lambda kv: (kv[1].f1, kv[0]))
    top5 = ranked[-5:][::-1]
    bottom5 = ranked[:5]
    lines = ["## Top 5 épisodes (F1)", "",
             "| Épisode | F1 | Precision | Recall |", "|---|---|---|---|"]
    for guid, m in top5:
        lines.append(
            f"| {guid} | {_fmt_pct(m.f1)} | "
            f"{_fmt_pct(m.precision)} | {_fmt_pct(m.recall)} |",
        )
    lines.append("")
    lines += ["## Bottom 5 épisodes (F1)", "",
              "| Épisode | F1 | Precision | Recall |", "|---|---|---|---|"]
    for guid, m in bottom5:
        lines.append(
            f"| {guid} | {_fmt_pct(m.f1)} | "
            f"{_fmt_pct(m.precision)} | {_fmt_pct(m.recall)} |",
        )
    lines.append("")
    return lines


def render_markdown(
    result: EvalResult | EvalMetrics, *, title: str = "Eval report",
) -> str:
    """Sérialise ``result`` en Markdown."""
    lines: list[str] = [f"# {title}", ""]
    lines += _render_summary(result)
    if isinstance(result, EvalMetrics):
        lines += _render_per_episode_summary(result)
    lines += ["## Détails", "",
              "| Verdict | Attendue | Matchée | Score |",
              "|---|---|---|---|"]
    for d in _details_iter(result):
        score = d.get("score", "")
        score_s = f"{score:.3f}" if isinstance(score, float) else str(score)
        matched = d.get("matched_title") or d.get("extracted_title", "")
        lines.append(
            f"| {d.get('verdict', '')} | {d.get('expected_title', '')} | "
            f"{matched} | {score_s} |",
        )
    return "\n".join(lines) + "\n"


def write_markdown(
    result: EvalResult | EvalMetrics, path: str | Path,
    *, title: str = "Eval report",
) -> Path:
    """Écrit le rapport markdown à ``path``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_markdown(result, title=title), encoding="utf-8")
    return p


@register_reporter("markdown")
class MarkdownReporter:
    """Reporter Markdown (implémente le Protocol ``EvalReporter``)."""

    def render(
        self, metrics: EvalResult | EvalMetrics, *, title: str = "Eval report",
    ) -> str:
        return render_markdown(metrics, title=title)

    def write(
        self, metrics: EvalResult | EvalMetrics, path: str | Path,
        *, title: str = "Eval report",
    ) -> Path:
        return write_markdown(metrics, path, title=title)
