"""Tests rétro-compat Severity legacy sidecars (T-02, ADR 0019).

Garantit qu'un sidecar produit AVANT la migration audit_core continue
de se lire. Couvre :

- ``match_audit`` v0 (sans ``schemaVersion``) — R-01.
- ``enrich_audit`` v1 (déjà versionné).
- Inter-opérabilité ``Severity`` 4-niveaux (option B ADR 0019).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit_core.types import Severity, coerce_severity


# ---------------------------------------------------------------------------
# match_audit — sidecar v0 (legacy, sans schemaVersion) → lecture rétro-compat
# ---------------------------------------------------------------------------


def test_match_audit_legacy_sidecar_v0_reads(tmp_path: Path, caplog) -> None:
    """Un sidecar match_audit v0 (sans schemaVersion) est lu avec un
    warning log mais reste fonctionnel (R-01 ADR 0019)."""
    from tools.match_audit.sidecar import read_sidecar, sidecar_path

    path = sidecar_path("src", "abc123", base_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Payload legacy (pas de schemaVersion)
    legacy_payload = {
        "episodeGuid": "abc123",
        "matchSuspect": True,
        "suspicions": [
            {"kind": "duration_mismatch", "detail": "23%", "severity": "error"}
        ],
        "auditedAt": "2026-05-01T12:00:00Z",
    }
    path.write_text(
        json.dumps(legacy_payload), encoding="utf-8",
    )

    import logging
    with caplog.at_level(logging.WARNING, logger="reco.match_audit.sidecar"):
        raw = read_sidecar("src", "abc123", base_dir=tmp_path)

    assert raw is not None
    assert raw["episodeGuid"] == "abc123"
    assert raw["suspicions"][0]["severity"] == "error"
    # Warning loggué pour signaler le legacy.
    assert any("legacy" in rec.message.lower() for rec in caplog.records)


def test_match_audit_new_sidecar_v1_has_schema_version(tmp_path: Path) -> None:
    """Un sidecar produit MAINTENANT inclut ``schemaVersion: 1``."""
    from tools.match_audit.service import MatchAuditResult
    from tools.match_audit.sidecar import (
        SIDECAR_SCHEMA_VERSION,
        sidecar_path,
        write_sidecar,
    )
    from tools.match_audit.types import MatchSuspicion

    susp = MatchSuspicion(
        kind="duration_mismatch", detail="23%", severity=Severity.ERROR,
    )
    res = MatchAuditResult(
        episode_guid="abc123", is_suspect=True, suspicions=(susp,),
    )
    write_sidecar(res, "src", base_dir=tmp_path)
    p = sidecar_path("src", "abc123", base_dir=tmp_path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == SIDECAR_SCHEMA_VERSION == 1


def test_match_audit_v1_sidecar_read_no_warning(
    tmp_path: Path, caplog,
) -> None:
    """Un sidecar v1 ne déclenche AUCUN warning legacy."""
    from tools.match_audit.service import MatchAuditResult
    from tools.match_audit.sidecar import read_sidecar, write_sidecar
    from tools.match_audit.types import MatchSuspicion

    susp = MatchSuspicion(
        kind="duration_mismatch", detail="23%", severity=Severity.ERROR,
    )
    res = MatchAuditResult(
        episode_guid="abc123", is_suspect=True, suspicions=(susp,),
    )
    write_sidecar(res, "src", base_dir=tmp_path)

    import logging
    with caplog.at_level(logging.WARNING, logger="reco.match_audit.sidecar"):
        raw = read_sidecar("src", "abc123", base_dir=tmp_path)
    assert raw is not None
    assert not any("legacy" in rec.message.lower() for rec in caplog.records)


# ---------------------------------------------------------------------------
# Inter-op Severity — chaque module accepte le 4-niveaux unifié à la lecture
# ---------------------------------------------------------------------------


def test_severity_match_audit_legacy_e_w_still_coerce() -> None:
    """Les sidecars match_audit historiques avec ``error``/``warning``
    se lisent toujours."""
    assert coerce_severity("error") is Severity.ERROR
    assert coerce_severity("warning") is Severity.WARNING


def test_severity_enrich_audit_legacy_i_w_c_still_coerce() -> None:
    """Les sidecars enrich_audit historiques (info/warning/critical) se
    lisent toujours."""
    assert coerce_severity("info") is Severity.INFO
    assert coerce_severity("warning") is Severity.WARNING
    assert coerce_severity("critical") is Severity.CRITICAL


def test_severity_enrich_audit_module_severity_is_audit_core() -> None:
    """Les modules réexportent bien la même classe (object identity)."""
    import tools.match_audit.types as mt
    import enrich_audit.types as et
    from audit_core.types import Severity as core_severity

    assert mt.Severity is core_severity
    assert et.Severity is core_severity


def test_enrich_audit_sidecar_uses_audit_core_severity(
    tmp_path: Path,
) -> None:
    """Un sidecar enrich_audit produit MAINTENANT sérialise correctement
    Severity 4-niveaux."""
    from enrich_audit.flag_writer import sidecar_path, write_sidecar
    from enrich_audit.service import AuditResult
    from enrich_audit.types import Suspicion

    susps = (
        Suspicion(kind="title_mismatch", detail="X != Y", severity=Severity.WARNING),
        Suspicion(kind="type_mismatch", detail="movie vs tv", severity=Severity.CRITICAL),
    )
    res = AuditResult(item_id="abc", is_suspect=True, suspicions=susps)
    write_sidecar(res, "src", base_dir=tmp_path, audited_at="2026-06-10T00:00:00Z")
    p = sidecar_path("src", "abc", base_dir=tmp_path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    severities = {s["severity"] for s in payload["suspicions"]}
    assert "warning" in severities
    assert "critical" in severities
