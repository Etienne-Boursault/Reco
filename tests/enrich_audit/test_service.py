"""Tests : tools.enrich_audit.service — value objects + orchestration."""
from __future__ import annotations

import pytest

from domain.item import ExternalIds, Item, ItemType
from enrich_audit.service import (
    AuditResult,
    EnrichAuditService,
    SourceAuditReport,
)
from enrich_audit.types import Severity, Suspicion


# ===== Suspicion (VO) ======================================================


def test_suspicion_valid_construction():
    s = Suspicion(kind="x", detail="d", severity=Severity.WARNING)
    assert s.kind == "x"
    assert s.severity is Severity.WARNING
    assert s.confidence is None


def test_suspicion_default_severity_is_warning():
    s = Suspicion(kind="x", detail="d")
    assert s.severity is Severity.WARNING


def test_suspicion_accepts_confidence():
    s = Suspicion(kind="x", detail="d", confidence=0.7)
    assert s.confidence == 0.7


def test_suspicion_rejects_empty_kind():
    with pytest.raises(ValueError):
        Suspicion(kind="", detail="d")


def test_suspicion_rejects_non_string_kind():
    with pytest.raises(ValueError):
        Suspicion(kind=42, detail="d")  # type: ignore[arg-type]


def test_suspicion_rejects_non_string_detail():
    with pytest.raises(ValueError):
        Suspicion(kind="x", detail=42)  # type: ignore[arg-type]


def test_suspicion_rejects_non_severity_enum():
    with pytest.raises(ValueError):
        Suspicion(kind="x", detail="d", severity="warning")  # type: ignore[arg-type]


def test_suspicion_rejects_confidence_out_of_range():
    with pytest.raises(ValueError):
        Suspicion(kind="x", detail="d", confidence=1.5)
    with pytest.raises(ValueError):
        Suspicion(kind="x", detail="d", confidence=-0.1)


def test_suspicion_rejects_bool_confidence():
    with pytest.raises(ValueError):
        Suspicion(kind="x", detail="d", confidence=True)  # type: ignore[arg-type]


def test_suspicion_rejects_non_numeric_confidence():
    with pytest.raises(ValueError):
        Suspicion(kind="x", detail="d", confidence="0.5")  # type: ignore[arg-type]


# ===== AuditResult (VO) ====================================================


def test_audit_result_clean():
    r = AuditResult(item_id="x", is_suspect=False, suspicions=())
    assert r.is_suspect is False


def test_audit_result_rejects_empty_item_id():
    with pytest.raises(ValueError):
        AuditResult(item_id="", is_suspect=False, suspicions=())


def test_audit_result_rejects_inconsistent_state_suspect_without_suspicions():
    with pytest.raises(ValueError):
        AuditResult(item_id="x", is_suspect=True, suspicions=())


def test_audit_result_rejects_inconsistent_state_clean_with_suspicions():
    with pytest.raises(ValueError):
        AuditResult(
            item_id="x",
            is_suspect=False,
            suspicions=(Suspicion(kind="k", detail="d"),),
        )


def test_audit_result_rejects_non_tuple_suspicions():
    with pytest.raises(ValueError):
        AuditResult(item_id="x", is_suspect=False, suspicions=[])  # type: ignore[arg-type]


# ===== Service =============================================================


def _item(tmdb: int | None = 42) -> Item:
    return Item(
        id="abc12345",
        types=(ItemType.FILM,),
        title="Test",
        external_ids=ExternalIds(tmdb=tmdb, tmdb_type="movie") if tmdb else ExternalIds(),
    )


def test_service_requires_at_least_one_check():
    with pytest.raises(ValueError):
        EnrichAuditService(checks=[])


def test_audit_item_returns_none_if_no_tmdb_id():
    svc = EnrichAuditService(checks=[lambda i, d: None])
    assert svc.audit_item(_item(tmdb=None), lambda _id: {"x": 1}) is None


def test_audit_item_returns_none_if_provider_has_no_data():
    svc = EnrichAuditService(checks=[lambda i, d: None])
    assert svc.audit_item(_item(), lambda _id: None) is None


def test_audit_item_returns_clean_when_all_checks_pass():
    svc = EnrichAuditService(checks=[lambda i, d: None, lambda i, d: None])
    result = svc.audit_item(_item(), lambda _id: {})
    assert result is not None
    assert result.is_suspect is False
    assert result.item_id == "abc12345"


def test_audit_item_aggregates_suspicions():
    s1 = Suspicion(kind="a", detail="x")
    s2 = Suspicion(kind="b", detail="y")
    svc = EnrichAuditService(checks=[lambda i, d: s1, lambda i, d: None, lambda i, d: s2])
    result = svc.audit_item(_item(), lambda _id: {})
    assert result is not None
    assert result.is_suspect is True
    assert result.suspicions == (s1, s2)


def test_audit_item_passes_correct_tmdb_id_to_provider():
    seen: list[int] = []

    def provider(tmdb_id: int) -> dict:
        seen.append(tmdb_id)
        return {}

    svc = EnrichAuditService(checks=[lambda i, d: None])
    svc.audit_item(_item(tmdb=777), provider)
    assert seen == [777]


def test_audit_item_isolates_check_exceptions():
    """CR senior H6 : une exception dans un check ne crashe pas l'audit."""
    def boom(item, data):
        raise RuntimeError("kaboom")

    good = Suspicion(kind="ok", detail="d")

    svc = EnrichAuditService(checks=[boom, lambda i, d: good])
    result = svc.audit_item(_item(), lambda _id: {})
    assert result is not None
    assert result.suspicions == (good,)


def test_audit_items_skips_items_without_tmdb():
    svc = EnrichAuditService(checks=[lambda i, d: None])
    items = [_item(tmdb=None), _item(tmdb=1)]
    report = svc.audit_items("src", items, lambda _id: {})
    assert report.audited_count == 1
    assert report.skipped_no_tmdb == 1
    assert report.skipped_no_cache == 0


def test_audit_items_skips_items_with_no_cache():
    svc = EnrichAuditService(checks=[lambda i, d: None])
    report = svc.audit_items("src", [_item(tmdb=1)], lambda _id: None)
    assert report.audited_count == 0
    assert report.skipped_no_cache == 1


def test_audit_items_counts_check_errors():
    """CR senior H6 : compteur dédié aux check-errors."""
    def boom(item, data):
        raise ValueError("nope")

    svc = EnrichAuditService(checks=[boom])
    report = svc.audit_items("src", [_item(tmdb=1)], lambda _id: {})
    assert report.audited_count == 1
    assert report.skipped_check_error == 1


def test_audit_items_aggregates_report_counts():
    bad = Suspicion(kind="x", detail="y")
    svc = EnrichAuditService(checks=[lambda i, d: bad if i.id == "abc12345" else None])
    items = [
        _item(tmdb=1),
        Item(id="def67890", types=(ItemType.FILM,), title="OK",
             external_ids=ExternalIds(tmdb=2, tmdb_type="movie")),
    ]
    report = svc.audit_items("src", items, lambda _id: {})
    assert report.audited_count == 2
    assert report.suspect_count == 1
    assert report.clean_count == 1
    assert report.source_id == "src"
    # CR senior L9 : skipped_* explicitement vérifiés.
    assert report.skipped_no_tmdb == 0
    assert report.skipped_no_cache == 0
    assert report.skipped_check_error == 0
