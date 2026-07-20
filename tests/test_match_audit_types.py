"""Tests : tools.match_audit.types — MatchSuspicion + Severity."""
from __future__ import annotations

import pytest

from tools.match_audit.types import (
    KNOWN_KINDS,
    MatchSuspicion,
    Severity,
    coerce_severity,
    severity_value,
)


def test_severity_values_serialized():
    assert Severity.ERROR.value == "error"
    assert Severity.WARNING.value == "warning"
    assert severity_value(Severity.ERROR) == "error"
    assert severity_value("warning") == "warning"


def test_coerce_severity_round_trip():
    assert coerce_severity("error") is Severity.ERROR
    assert coerce_severity(Severity.WARNING) is Severity.WARNING


def test_coerce_severity_invalid_string_raises():
    # ADR 0019 (option B) : Severity unifié 4 niveaux. "info" est désormais
    # valide (réexport audit_core.Severity). Cette assertion historique
    # de match_audit (E/W seuls) est obsolète — on teste maintenant une
    # vraie chaîne inconnue.
    with pytest.raises(ValueError):
        coerce_severity("blocker")


def test_coerce_severity_invalid_type_raises():
    with pytest.raises(TypeError):
        coerce_severity(42)


def test_match_suspicion_requires_severity_explicit():
    """CR archi #26 — severity OBLIGATOIRE, plus de défaut `error`."""
    with pytest.raises(TypeError):
        MatchSuspicion(kind="duration_mismatch", detail="x")  # type: ignore[call-arg]


def test_match_suspicion_rejects_empty_kind():
    with pytest.raises(ValueError):
        MatchSuspicion(kind="", detail="x", severity=Severity.ERROR)


def test_match_suspicion_rejects_non_string_detail():
    with pytest.raises(ValueError):
        MatchSuspicion(
            kind="k", detail=123, severity=Severity.ERROR,  # type: ignore[arg-type]
        )


def test_match_suspicion_rejects_raw_string_severity():
    with pytest.raises(ValueError):
        MatchSuspicion(
            kind="k", detail="x", severity="error",  # type: ignore[arg-type]
        )


def test_known_kinds_documents_three():
    assert {"duration_mismatch", "intro_mismatch", "title_drift"} <= KNOWN_KINDS


def test_match_suspicion_is_frozen():
    s = MatchSuspicion(kind="k", detail="d", severity=Severity.ERROR)
    with pytest.raises(Exception):
        s.detail = "x"  # type: ignore[misc]
