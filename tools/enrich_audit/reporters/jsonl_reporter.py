"""Reporter JSONL — append-only log par item suspect (CR senior H9).

Format : 1 ligne JSON par item suspect, écrit dans
``tools/output/logs/audit_tmdb.jsonl`` (ou path injecté).

Utile pour :
  - timeline des audits (debug régression matcher TMDB) ;
  - input d'un futur dashboard.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..service import SourceAuditReport


def write_jsonl_log(
    report: SourceAuditReport,
    *,
    log_path: Path,
    timestamp: str | None = None,
) -> int:
    """Append une ligne JSONL par item suspect. Renvoie le nb écrit.

    Idempotent au niveau "ne casse rien si appelé plusieurs fois" (append),
    pas au niveau "produit la même sortie" — c'est un log temporel.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = 0
    lines = []
    for r in sorted(report.results, key=lambda r: r.item_id):
        if not r.is_suspect:
            continue
        line = {
            "ts": ts,
            "source": report.source_id,
            "itemId": r.item_id,
            "kinds": sorted({s.kind for s in r.suspicions}),
            "severities": sorted({s.severity.value for s in r.suspicions}),
        }
        lines.append(json.dumps(line, ensure_ascii=False, sort_keys=True))
        written += 1
    if lines:
        with log_path.open("a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
    return written


__all__ = ["write_jsonl_log"]
