"""Tests audit_core.types — Severity, Suspicion, Check."""
from __future__ import annotations

import pytest

from audit_core.types import (
    Check,
    Severity,
    Suspicion,
    coerce_severity,
    severity_rank,
    severity_value,
)


class TestSeverity:
    def test_four_levels_string_values(self) -> None:
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.ERROR.value == "error"
        assert Severity.CRITICAL.value == "critical"

    def test_is_str_enum(self) -> None:
        # StrEnum : la comparaison avec str fonctionne directement.
        assert Severity.WARNING == "warning"
        assert str(Severity.ERROR) == "error"

    def test_legacy_match_audit_values_load(self) -> None:
        # rétro-compat sidecars match_audit (E/W).
        assert Severity("error") is Severity.ERROR
        assert Severity("warning") is Severity.WARNING

    def test_legacy_enrich_audit_values_load(self) -> None:
        # rétro-compat sidecars enrich_audit (I/W/C).
        assert Severity("info") is Severity.INFO
        assert Severity("warning") is Severity.WARNING
        assert Severity("critical") is Severity.CRITICAL


class TestSeverityRank:
    def test_ranks_monotone(self) -> None:
        assert severity_rank(Severity.INFO) < severity_rank(Severity.WARNING)
        assert severity_rank(Severity.WARNING) < severity_rank(Severity.ERROR)
        assert severity_rank(Severity.ERROR) < severity_rank(Severity.CRITICAL)

    def test_ranks_concrete(self) -> None:
        assert severity_rank(Severity.INFO) == 0
        assert severity_rank(Severity.CRITICAL) == 3

    def test_ranks_type_error_on_str(self) -> None:
        with pytest.raises(TypeError):
            severity_rank("warning")  # type: ignore[arg-type]


class TestCoerceSeverity:
    def test_passthrough_enum(self) -> None:
        assert coerce_severity(Severity.WARNING) is Severity.WARNING

    def test_str_to_enum(self) -> None:
        assert coerce_severity("critical") is Severity.CRITICAL

    def test_invalid_str_raises_valueerror(self) -> None:
        with pytest.raises(ValueError, match="Severity inconnue"):
            coerce_severity("blocker")

    def test_invalid_type_raises_typeerror(self) -> None:
        with pytest.raises(TypeError):
            coerce_severity(42)


class TestSeverityValue:
    def test_enum(self) -> None:
        assert severity_value(Severity.ERROR) == "error"

    def test_str_passthrough(self) -> None:
        assert severity_value("warning") == "warning"


class TestSuspicion:
    def test_create_minimal(self) -> None:
        s = Suspicion(kind="x", detail="d")
        assert s.kind == "x"
        assert s.severity is Severity.WARNING  # défaut

    def test_create_with_severity(self) -> None:
        s = Suspicion(kind="x", detail="d", severity=Severity.CRITICAL)
        assert s.severity is Severity.CRITICAL

    def test_frozen(self) -> None:
        s = Suspicion(kind="x", detail="d")
        with pytest.raises((AttributeError, TypeError)):
            s.kind = "y"  # type: ignore[misc]

    def test_kind_must_be_nonempty_str(self) -> None:
        with pytest.raises(ValueError):
            Suspicion(kind="", detail="d")
        with pytest.raises(ValueError):
            Suspicion(kind=None, detail="d")  # type: ignore[arg-type]

    def test_detail_must_be_str(self) -> None:
        with pytest.raises(ValueError):
            Suspicion(kind="x", detail=42)  # type: ignore[arg-type]

    def test_severity_must_be_enum(self) -> None:
        with pytest.raises(ValueError):
            Suspicion(kind="x", detail="d", severity="warning")  # type: ignore[arg-type]


class _DuckCheck:
    name = "title_drift"
    kind = "title_mismatch"
    description = "Compare titles"

    def __call__(self, *args, **kwargs):  # noqa: ANN
        return None


class TestCheckProtocol:
    def test_isinstance_protocol_structural(self) -> None:
        assert isinstance(_DuckCheck(), Check)

    def test_non_conforming_rejected(self) -> None:
        class Missing:
            name = "x"
            # pas de kind ni description ni __call__

        assert not isinstance(Missing(), Check)
