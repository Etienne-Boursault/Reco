"""Tests : tools.match_audit.service.MatchAuditService."""
from __future__ import annotations

import pytest

from tools.match_audit.service import (
    MatchAuditResult,
    MatchAuditService,
    SourceAuditReport,
    compute_should_flag,
)
from tools.match_audit.types import MatchSuspicion, Severity


def _suspicion(
    kind: str = "duration_mismatch", severity: Severity = Severity.ERROR,
) -> MatchSuspicion:
    return MatchSuspicion(kind=kind, detail="x", severity=severity)


# ---------------------------------------------------------------------------
# compute_should_flag (CR archi #20)
# ---------------------------------------------------------------------------


def test_compute_should_flag_empty_is_false():
    assert compute_should_flag(()) is False


def test_compute_should_flag_only_warning_is_false():
    assert compute_should_flag((_suspicion(severity=Severity.WARNING),)) is False


def test_compute_should_flag_any_error_is_true():
    s = (
        _suspicion(severity=Severity.WARNING),
        _suspicion(severity=Severity.ERROR),
    )
    assert compute_should_flag(s) is True


# ---------------------------------------------------------------------------
# Service construction (CR senior H4)
# ---------------------------------------------------------------------------


def test_service_empty_checks_raises():
    with pytest.raises(ValueError, match="au moins un check"):
        MatchAuditService(checks=[])


def test_service_exposes_immutable_checks_tuple():
    f = lambda ep: None  # noqa: E731
    svc = MatchAuditService(checks=[f])
    assert svc.checks == (f,)
    assert isinstance(svc.checks, tuple)


# ---------------------------------------------------------------------------
# audit_episode
# ---------------------------------------------------------------------------


def test_audit_episode_one_check_suspicious():
    svc = MatchAuditService(checks=[lambda ep: _suspicion()])
    res = svc.audit_episode({"guid": "g2"})
    assert isinstance(res, MatchAuditResult)
    assert res.is_suspect is True
    assert res.should_flag is True
    assert res.has_findings is True
    assert len(res.suspicions) == 1


def test_audit_episode_warning_only_not_suspect():
    """Un warning seul ne flag pas suspect (que les `error` flagguent)."""
    warn = _suspicion(severity=Severity.WARNING)
    svc = MatchAuditService(checks=[lambda ep: warn])
    res = svc.audit_episode({"guid": "g4"})
    assert res is not None
    assert res.is_suspect is False
    assert res.has_findings is True
    assert len(res.suspicions) == 1


def test_audit_episode_aggregates_multiple_checks():
    svc = MatchAuditService(checks=[
        lambda ep: None,
        lambda ep: _suspicion("title_drift", Severity.WARNING),
        lambda ep: _suspicion("intro_mismatch", Severity.ERROR),
    ])
    res = svc.audit_episode({"guid": "g3"})
    assert res is not None
    assert res.is_suspect is True
    assert {s.kind for s in res.suspicions} == {"title_drift", "intro_mismatch"}


def test_audit_episode_skips_when_guid_missing():
    """CR senior C1 — guid absent → on retourne None (skip), pas un verdict
    indexé par chaîne vide."""
    svc = MatchAuditService(checks=[lambda ep: None])
    assert svc.audit_episode({}) is None


# ---------------------------------------------------------------------------
# MatchAuditResult invariants (CR senior H3)
# ---------------------------------------------------------------------------


def test_result_rejects_empty_guid():
    with pytest.raises(ValueError):
        MatchAuditResult(episode_guid="", is_suspect=False, suspicions=())


def test_result_rejects_non_tuple_suspicions():
    with pytest.raises(ValueError):
        MatchAuditResult(
            episode_guid="g", is_suspect=False,
            suspicions=[],  # type: ignore[arg-type]
        )


def test_source_report_rejects_non_tuple_results():
    with pytest.raises(ValueError):
        SourceAuditReport(
            source_id="src", total=0, results=[],  # type: ignore[arg-type]
        )


def test_source_report_rejects_inconsistent_total():
    with pytest.raises(ValueError):
        SourceAuditReport(source_id="src", total=5, results=())


def test_result_rejects_inconsistent_is_suspect():
    susp = _suspicion(severity=Severity.ERROR)
    with pytest.raises(ValueError):
        MatchAuditResult(episode_guid="g", is_suspect=False, suspicions=(susp,))


# ---------------------------------------------------------------------------
# audit_source (CR senior M7, CR archi #13, #31)
# ---------------------------------------------------------------------------


def test_audit_source_counts_clean_suspect_warnings():
    svc = MatchAuditService(checks=[
        lambda ep: _suspicion() if ep["guid"] == "bad" else
        (_suspicion("title_drift", Severity.WARNING)
         if ep["guid"] == "warn" else None),
    ])
    report = svc.audit_source(
        "src-x",
        [{"guid": "ok"}, {"guid": "bad"}, {"guid": "warn"}],
    )
    assert report.source_id == "src-x"
    assert report.total == 3
    assert report.audited_count == 3
    assert report.suspect_count == 1
    assert report.clean_count == 1
    assert report.warning_only_count == 1
    assert report.audited_episode_guids == ("ok", "bad", "warn")


def test_audit_source_skips_no_guid():
    svc = MatchAuditService(checks=[lambda ep: None])
    report = svc.audit_source(
        "src", [{"guid": "ok"}, {"no-guid": "x"}, {"guid": ""}],
    )
    assert report.audited_count == 1
    assert report.skipped_no_guid == 2


def test_audit_source_counts_skipped_no_duration_and_no_title():
    svc = MatchAuditService(checks=[lambda ep: None])
    report = svc.audit_source("src", [
        {"guid": "g1", "title": "t", "youtubeTitle": "y",
         "audioDuration": 100, "youtubeDuration": 100},
        {"guid": "g2", "title": "t", "youtubeTitle": None,
         "audioDuration": None, "youtubeDuration": None},
    ])
    assert report.skipped_no_duration == 1
    assert report.skipped_no_title == 1


def test_audit_source_counts_skipped_no_transcript():
    svc = MatchAuditService(checks=[lambda ep: None])
    report = svc.audit_source("src", [
        {"guid": "g1", "transcriptStatus": "auto"},
        {"guid": "g2", "transcriptStatus": "none"},
    ])
    assert report.skipped_no_transcript == 1


def test_audit_source_empty():
    svc = MatchAuditService(checks=[lambda ep: None])
    report = svc.audit_source("src", [])
    assert report.total == 0
    assert report.audited_count == 0
    assert report.suspect_count == 0


def test_audit_episode_accepts_episode_view():
    """Le service accepte aussi un EpisodeView (typed)."""
    from tools.match_audit.protocols import EpisodeView
    view = EpisodeView.from_dict({"guid": "g1"})
    assert view is not None
    svc = MatchAuditService(checks=[lambda ep: None])
    res = svc.audit_episode(view)
    assert res is not None and res.episode_guid == "g1"


def test_audit_episode_class_check_with_dict_payload():
    """Branche : check protocol + payload dict → conversion en view."""
    from tools.match_audit.protocols import EpisodeView

    class FakeCheck:
        kind = "k"
        severity = Severity.ERROR
        description = "d"

        def check(self, ep: EpisodeView):
            return None

    svc = MatchAuditService(checks=[FakeCheck()])
    # On passe un dict, le service convertit en EpisodeView en interne.
    res = svc.audit_episode({"guid": "g1"})
    assert res is not None


def test_audit_episode_invokes_class_check_with_view():
    """Une check classe (Protocol MatchCheck) reçoit une EpisodeView."""
    from dataclasses import dataclass
    from tools.match_audit.protocols import EpisodeView
    seen: dict = {}

    @dataclass
    class FakeCheck:
        kind: str = "duration_mismatch"
        severity: Severity = Severity.ERROR
        description: str = "x"

        def check(self, ep: EpisodeView):
            seen["view"] = ep
            return None

    svc = MatchAuditService(checks=[FakeCheck()])
    svc.audit_episode({"guid": "g1"})
    assert isinstance(seen["view"], EpisodeView)


def test_audit_episode_rejects_non_mapping():
    svc = MatchAuditService(checks=[lambda ep: None])
    assert svc.audit_episode("not-a-dict") is None  # type: ignore[arg-type]


def test_audit_source_handles_non_mapping_input():
    """Si un élément n'est même pas un mapping, on skip proprement."""
    svc = MatchAuditService(checks=[lambda ep: None])
    # On contourne le type-checker pour passer un non-mapping.
    report = svc.audit_source("src", [{"guid": "g1"}, "garbage"])  # type: ignore[list-item]
    assert report.skipped_no_guid == 1
    assert report.audited_count == 1


def test_source_report_invariant_total_equals_audited_plus_skipped():
    """CR archi #31 — invariant validé."""
    svc = MatchAuditService(checks=[lambda ep: None])
    report = svc.audit_source("src", [{"guid": "ok"}, {"no": "guid"}])
    assert report.audited_count + report.skipped_no_guid == report.total
