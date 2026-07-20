"""Reporter JSON — output canonique du rapport (stdout / piping CI)."""
from __future__ import annotations

import json

from ..service import SourceAuditReport


def format_json(report: SourceAuditReport) -> str:
    payload = {
        "sourceId": report.source_id,
        "audited": report.audited_count,
        "suspect": report.suspect_count,
        "clean": report.clean_count,
        "skippedNoTmdb": report.skipped_no_tmdb,
        "skippedNoCache": report.skipped_no_cache,
        "skippedCheckError": report.skipped_check_error,
        "skippedCacheVersionMismatch": report.skipped_cache_version_mismatch,
        "sidecarMalformed": report.sidecar_malformed,
        "results": [
            {
                "itemId": r.item_id,
                "enrichmentSuspect": r.is_suspect,
                "suspicions": [
                    {
                        "kind": s.kind,
                        "detail": s.detail,
                        "severity": s.severity.value,
                        "confidence": s.confidence,
                    }
                    for s in r.suspicions
                ],
            }
            for r in sorted(report.results, key=lambda r: r.item_id)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


__all__ = ["format_json"]
