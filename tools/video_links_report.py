"""Agrégats et rendu du rapport d'une passe d'enrichissement vidéo.

Il ne décide de rien : il compte, il classe, il met en forme. Les codes de
raison qu'il agrège viennent de `video_links_matching` et doivent rester
STABLES — ce sont eux qui permettent de comparer deux passes.

Extrait de `enrich_video_links.py` (cf. `video_links_matching`).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Les garde-fous de recherche par titre sont CALIBRÉS SUR MESURE RÉELLE dans
# `enrich_creators` (cf. `obscurity_verdict`). On les importe : en écrire
# d'autres reviendrait à recalibrer à l'aveugle.
from video_links_matching import (
    ALL_SITES,
    AMBIGUOUS_REASONS,
    LINKS_DISPLAY_CAP,
    REASON_FILLED,
    SITE_LABELS,
    Resolution,
    video_type,
)


@dataclass(frozen=True)
class FilledCase:
    reco_id: str
    title: str
    type_: str
    population: str
    links: tuple[dict[str, Any], ...]
    source: str
    total_after: int
    path: Path


@dataclass(frozen=True)
class ReviewCase:
    reco_id: str
    title: str
    type_: str
    population: str | None
    reason: str
    detail: str
    source: str | None


@dataclass
class Report:
    """Agrégats d'une passe (`run`), séparés par population."""

    seen: int = 0
    written: int = 0
    filled: list[FilledCase] = field(default_factory=list)
    review: list[ReviewCase] = field(default_factory=list)
    truncated: list[str] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)
    by_population: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter))
    links_by_site: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter))
    reasons_by_population: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter))

    def record(self, reco: dict[str, Any], resolution: Resolution, path: Path,
               total_after: int) -> None:
        """Enregistre le sort d'une reco."""
        self.skipped[resolution.reason] += 1
        pop = resolution.population
        if pop is not None:
            self.reasons_by_population[pop][resolution.reason] += 1
            self.by_population[pop]["recos"] += 1

        if not resolution.links:
            if resolution.reason in AMBIGUOUS_REASONS:
                self.review.append(ReviewCase(
                    reco.get("id", path.stem), reco.get("title", ""),
                    video_type(reco), pop, resolution.reason,
                    resolution.detail, resolution.source))
            return

        self.filled.append(FilledCase(
            reco.get("id", path.stem), reco.get("title", ""), video_type(reco),
            pop, resolution.links, resolution.source or "?", total_after, path))
        self.by_population[pop]["links"] += len(resolution.links)
        for link in resolution.links:
            self.links_by_site[pop][link["label"]] += 1
        if total_after > LINKS_DISPLAY_CAP:
            self.truncated.append(reco.get("id", path.stem))


def format_report(report: Report) -> str:
    """Rapport lisible : une ligne par population, détail par site."""
    header = (f"{'population':14} {'recos':>6} {'liens':>6} "
              + " ".join(f"{SITE_LABELS[s]:>10}" for s in ALL_SITES)
              + "  refus dominant")
    lines = ["", header, "-" * len(header)]
    for pop in sorted(report.by_population):
        counts = report.by_population[pop]
        reasons = Counter({r: n for r, n in report.reasons_by_population[pop].items()
                           if r != REASON_FILLED})
        top = reasons.most_common(1)
        top_txt = f"{top[0][0]} ({top[0][1]})" if top else "—"
        per_site = " ".join(
            f"{report.links_by_site[pop][SITE_LABELS[s]]:>10}" for s in ALL_SITES)
        lines.append(f"{pop:14} {counts['recos']:6} {counts['links']:6} "
                     f"{per_site}  {top_txt}")
    total_links = sum(len(c.links) for c in report.filled)
    lines += [
        "-" * len(header),
        (f"Recos vues : {report.seen} · enrichies : {len(report.filled)} "
         f"· liens posés : {total_links} · fichiers écrits : {report.written}"),
        f"À revoir à la main : {len(report.review)}",
    ]
    if report.truncated:
        lines.append(f"⚠️  {len(report.truncated)} reco(s) passent au-delà des "
                     f"{LINKS_DISPLAY_CAP} liens affichés par RecoCard : "
                     f"{', '.join(report.truncated[:10])}")
    return "\n".join(lines)


def report_payload(report: Report) -> dict[str, Any]:
    """Version JSON-sérialisable du rapport (pour relecture humaine)."""
    return {
        "seen": report.seen,
        "written": report.written,
        "reasons": dict(report.skipped),
        "byPopulation": {p: dict(c) for p, c in sorted(report.by_population.items())},
        "linksBySite": {p: dict(c) for p, c in sorted(report.links_by_site.items())},
        "truncated": report.truncated,
        "filled": [
            {"id": c.reco_id, "title": c.title, "type": c.type_,
             "population": c.population, "source": c.source,
             "links": list(c.links), "totalAfter": c.total_after,
             "path": str(c.path)}
            for c in report.filled
        ],
        "review": [
            {"id": c.reco_id, "title": c.title, "type": c.type_,
             "population": c.population, "reason": c.reason,
             "detail": c.detail, "source": c.source}
            for c in report.review
        ],
    }
