"""audit_core — SSOT des primitives partagées par les modules d'audit.

Exposés ici :

- :class:`Severity` (4 niveaux unifiés — cf. ADR 0019)
- :class:`Suspicion` (VO base, composable)
- :class:`Check` (Protocol structurel)
- :func:`from_source_extra` (helper settings DRY)
- :func:`_safe_segment` (validation segments chemin)
- :func:`ensure_output_within` (anti-traversal)
- :func:`escape_md` (échappement MD union)
- :class:`Reporter` (Protocol structurel)
- :class:`RunOptionsBase`, :func:`utcnow_iso`
- :class:`JsonlAuditTrail`, :class:`NoopAuditTrail`

Les modules consommateurs (``lint``, ``match_audit``, ``enrich_audit``)
importent ces primitives plutôt que de redéfinir les leurs.
"""
from __future__ import annotations

from audit_core.cli_runner import (
    Mode,
    OutputFormat,
    RunOptionsBase,
    utcnow_iso,
)
from audit_core.reporters import REPORTERS, Reporter, escape_md
from audit_core.settings import from_source_extra
from audit_core.sidecar import _safe_segment, ensure_output_within
from audit_core.trail import AuditTrail, JsonlAuditTrail, NoopAuditTrail
from audit_core.types import (
    Check,
    CheckCallable,
    Severity,
    Suspicion,
    coerce_severity,
    severity_rank,
    severity_value,
)

__all__ = [
    "AuditTrail",
    "Check",
    "CheckCallable",
    "JsonlAuditTrail",
    "Mode",
    "NoopAuditTrail",
    "OutputFormat",
    "REPORTERS",
    "Reporter",
    "RunOptionsBase",
    "Severity",
    "Suspicion",
    "_safe_segment",
    "coerce_severity",
    "ensure_output_within",
    "escape_md",
    "from_source_extra",
    "severity_rank",
    "severity_value",
    "utcnow_iso",
]
