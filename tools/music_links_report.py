"""Agrégats et rendu du rapport d'une passe d'enrichissement musical.

Séparé du reste parce qu'il ne décide de rien : il compte, il classe, il met en
forme. Les codes de raison qu'il agrège viennent de `music_links_matching` et
doivent rester STABLES — ce sont eux qui permettent de comparer deux passes.

Extrait de `enrich_music_links.py` (cf. `music_links_matching`).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from music_links_matching import (
    AMBIGUOUS_REASONS,
    PLATFORMS,
    RecoOutcome,
    primary_type,
)


@dataclass(frozen=True)
class LinkedCase:
    reco_id: str
    title: str
    type_: str
    creator: str
    platform: str
    url: str
    source: str


@dataclass(frozen=True)
class ReviewCase:
    reco_id: str
    title: str
    type_: str
    platform: str
    reason: str
    detail: str


@dataclass
class Report:
    """Agrégats d'une passe (`run`)."""

    seen: int = 0
    written: int = 0
    linked: list[LinkedCase] = field(default_factory=list)
    review: list[ReviewCase] = field(default_factory=list)
    reasons: Counter = field(default_factory=Counter)
    by_platform: Counter = field(default_factory=Counter)
    by_type: dict[str, Counter] = field(
        default_factory=lambda: defaultdict(Counter))

    def record(self, reco: dict[str, Any], outcome: RecoOutcome) -> None:
        """Enregistre le sort d'une reco."""
        type_ = primary_type(reco)
        self.reasons[outcome.reason] += 1
        self.by_type[type_]["vues"] += 1
        reco_id = str(reco.get("id", ""))
        title = str(reco.get("title") or "")
        creator = str(reco.get("creator") or "")

        for link in outcome.links:
            self.by_platform[link.platform] += 1
            self.by_type[type_]["liens"] += 1
            self.linked.append(LinkedCase(reco_id, title, type_, creator,
                                          link.platform, link.url, link.source))
        for platform, reason, detail in outcome.refusals:
            if reason in AMBIGUOUS_REASONS:
                self.review.append(ReviewCase(reco_id, title, type_, platform,
                                              reason, detail))


def format_report(report: Report) -> str:
    """Rapport lisible : par type, puis par plateforme, puis les refus."""
    lines = [
        "",
        f"{'type':10} {'vues':>6} {'liens posés':>12}",
        "-" * 72,
    ]
    for type_ in sorted(report.by_type):
        counts = report.by_type[type_]
        lines.append(f"{type_:10} {counts['vues']:6} {counts['liens']:12}")
    lines += ["-" * 72, "Liens par plateforme :"]
    for platform, n in sorted(report.by_platform.items()):
        lines.append(f"  {PLATFORMS[platform]['label']:14} {n:5}")
    lines += ["Refus / raisons :"]
    for reason, n in report.reasons.most_common():
        lines.append(f"  {reason:26} {n:5}")
    lines += [
        "-" * 72,
        (f"Recos vues : {report.seen} · liens trouvés : {len(report.linked)} "
         f"· recos écrites : {report.written}"),
        f"À arbitrer à la main : {len(report.review)}",
    ]
    return "\n".join(lines)


def report_payload(report: Report) -> dict[str, Any]:
    """Version JSON-sérialisable du rapport (pour relecture humaine)."""
    return {
        "seen": report.seen,
        "written": report.written,
        "reasons": dict(report.reasons),
        "byPlatform": dict(report.by_platform),
        "byType": {t: dict(c) for t, c in sorted(report.by_type.items())},
        "linked": [
            {"id": c.reco_id, "title": c.title, "type": c.type_,
             "creator": c.creator, "platform": c.platform, "url": c.url,
             "source": c.source}
            for c in report.linked
        ],
        "review": [
            {"id": c.reco_id, "title": c.title, "type": c.type_,
             "platform": c.platform, "reason": c.reason, "detail": c.detail}
            for c in report.review
        ],
    }
