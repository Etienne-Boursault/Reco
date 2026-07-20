"""tools.enrich_audit — Audit post-enrichissement TMDB.

Détecte les enrichissements TMDB suspects (mauvaise œuvre matchée) via
plusieurs checks indépendants (similarité titre, écart d'année, cohérence
runtime ↔ type). Les verdicts sont écrits sous forme de **fichiers sidecar**
dans ``tools/output/enrich_audit/<source>/<item_id>.json``, jamais dans le
domaine `Item` lui-même (cf. ADR 0014).

API publique :
    - ``Suspicion`` : value object — un drapeau levé par un check
    - ``AuditResult`` : agrégat — verdict global pour un item
    - ``SourceAuditReport`` : agrégat — verdict pour une source entière
    - ``EnrichAuditService`` : orchestrateur — combine N checks
    - ``check_title_similarity`` / ``check_year_mismatch`` / ``check_runtime_coherence``
    - ``write_sidecar`` / ``read_sidecar`` : I/O sidecar
"""
from __future__ import annotations

from .runtime_coherence_check import check_runtime_coherence
from .service import (
    AuditResult,
    CheckFunction,
    EnrichAuditService,
    SourceAuditReport,
    Suspicion,
)
from .title_similarity_check import check_title_similarity
from .year_mismatch_check import check_year_mismatch
from .flag_writer import read_sidecar, sidecar_path, write_sidecar

__all__ = [
    "AuditResult",
    "CheckFunction",
    "EnrichAuditService",
    "SourceAuditReport",
    "Suspicion",
    "check_title_similarity",
    "check_year_mismatch",
    "check_runtime_coherence",
    "read_sidecar",
    "sidecar_path",
    "write_sidecar",
]
