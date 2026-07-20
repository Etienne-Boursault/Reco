"""Tests : tools.match_audit.cli_runner."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

import common
from tools.match_audit.cli_runner import (
    FileTranscriptRepo,
    RunOptions,
    default_service,
    emit_jsonl_events,
    format_human,
    format_json,
    format_markdown,
    index_paths_by_guid,
    load_episodes,
    report_as_dict,
    run_audit,
    trail_path_for_run,
    undo_last_apply,
)
from tools.match_audit.service import MatchAuditService
from tools.match_audit.settings import MatchAuditSettings


# ---------------------------------------------------------------------------
# FileTranscriptRepo  (CR senior C3/C4, CR archi #10)
# ---------------------------------------------------------------------------


def test_file_repo_returns_text_for_acast(tmp_path):
    base = tmp_path / "transcripts"
    src = base / "src1"
    src.mkdir(parents=True)
    (src / f"{common.slugify('g1')}.acast.txt").write_text("HELLO ACAST", encoding="utf-8")
    repo = FileTranscriptRepo("src1", base)
    assert repo.get("g1", "acast") == "HELLO ACAST"


def test_file_repo_returns_text_for_youtube(tmp_path):
    base = tmp_path / "transcripts"
    src = base / "src1"
    src.mkdir(parents=True)
    (src / f"{common.slugify('g1')}.youtube.txt").write_text("HELLO YT", encoding="utf-8")
    repo = FileTranscriptRepo("src1", base)
    assert repo.get("g1", "youtube") == "HELLO YT"


def test_file_repo_no_fallback_to_bare_txt(tmp_path):
    """CR senior C3 — un fichier ``<slug>.txt`` ne doit JAMAIS être servi à
    la fois comme acast et comme youtube (élimine le faux 'intro identique')."""
    base = tmp_path / "transcripts"
    src = base / "src1"
    src.mkdir(parents=True)
    (src / f"{common.slugify('g1')}.txt").write_text("AMBIGUOUS", encoding="utf-8")
    repo = FileTranscriptRepo("src1", base)
    assert repo.get("g1", "acast") is None
    assert repo.get("g1", "youtube") is None


def test_file_repo_kind_acast_yt_resolve_distinct_paths(tmp_path):
    """CR senior C4 — vérification d'intégration provider → file path :
    la convention `<slugify(guid)>.{kind}.txt` est respectée et les deux
    kinds résolvent vers des fichiers distincts."""
    base = tmp_path / "transcripts"
    src = base / "src1"
    src.mkdir(parents=True)
    (src / f"{common.slugify('My GUID/With éïô')}.acast.txt").write_text(
        "A", encoding="utf-8",
    )
    (src / f"{common.slugify('My GUID/With éïô')}.youtube.txt").write_text(
        "Y", encoding="utf-8",
    )
    repo = FileTranscriptRepo("src1", base)
    assert repo.get("My GUID/With éïô", "acast") == "A"
    assert repo.get("My GUID/With éïô", "youtube") == "Y"


def test_file_repo_unknown_kind_returns_none(tmp_path):
    base = tmp_path / "transcripts"
    repo = FileTranscriptRepo("src1", base)
    assert repo.get("g1", "spotify") is None  # type: ignore[arg-type]


def test_file_repo_empty_guid_returns_none(tmp_path):
    repo = FileTranscriptRepo("src1", tmp_path)
    assert repo.get("", "acast") is None


def test_file_repo_oserror_returns_none(tmp_path, monkeypatch):
    base = tmp_path / "transcripts"
    src = base / "src1"
    src.mkdir(parents=True)
    p = src / f"{common.slugify('g1')}.acast.txt"
    p.write_text("hello", encoding="utf-8")
    real_read = Path.read_text

    def boom(self, *a, **kw):
        if self.name == p.name:
            raise OSError("denied")
        return real_read(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", boom)
    assert FileTranscriptRepo("src1", base).get("g1", "acast") is None


def test_file_repo_no_resolve_when_oserror(tmp_path, monkeypatch):
    base = tmp_path / "transcripts"
    repo = FileTranscriptRepo("src1", base)

    def boom(self, *a, **kw):
        raise OSError("denied")

    monkeypatch.setattr(Path, "resolve", boom)
    assert repo.get("g1", "acast") is None


def test_file_repo_default_base(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "TRANSCRIPTS_DIR", tmp_path)
    (tmp_path / "src1").mkdir()
    p = tmp_path / "src1" / f"{common.slugify('g1')}.acast.txt"
    p.write_text("hi", encoding="utf-8")
    assert FileTranscriptRepo("src1").get("g1", "acast") == "hi"


# ---------------------------------------------------------------------------
# default_service (CR archi #4 + #5)
# ---------------------------------------------------------------------------


def test_default_service_builds_three_checks(tmp_path):
    svc = default_service("src", base_transcripts_dir=tmp_path)
    assert isinstance(svc, MatchAuditService)
    assert len(svc.checks) == 3


def test_default_service_enabled_checks_filters(tmp_path):
    s = MatchAuditSettings(enabled_checks=("duration_mismatch",))
    svc = default_service("src", settings=s, base_transcripts_dir=tmp_path)
    assert len(svc.checks) == 1


def test_default_service_uses_settings_threshold(tmp_path):
    """Les seuils du settings sont propagés aux check classes."""
    s = MatchAuditSettings(duration_tolerance=0.99)
    svc = default_service("src", settings=s, base_transcripts_dir=tmp_path)
    durs = [c for c in svc.checks if getattr(c, "kind", None) == "duration_mismatch"]
    assert durs and getattr(durs[0], "tolerance") == 0.99


# ---------------------------------------------------------------------------
# load_episodes / index_paths_by_guid
# ---------------------------------------------------------------------------


def _make_ep(d: Path, guid: str, audio: int, yt: int,
             title: str = "x", ytt: str = "y") -> Path:
    p = d / f"{guid}.json"
    p.write_text(json.dumps({
        "guid": guid, "sourceId": "src",
        "title": title, "youtubeTitle": ytt,
        "audioDuration": audio, "youtubeDuration": yt,
    }, ensure_ascii=False), encoding="utf-8")
    return p


def test_load_episodes_missing_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "missing")
    assert load_episodes("nope") == []


def test_load_episodes_skips_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.json").write_text("not json", encoding="utf-8")
    _make_ep(src, "g1", 100, 100)
    eps = load_episodes("src")
    assert len(eps) == 1


def test_load_episodes_skips_non_dict_payload(tmp_path, monkeypatch):
    """CR senior M6 — un JSON `[1,2,3]` est skippé proprement."""
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "list.json").write_text("[1,2,3]", encoding="utf-8")
    eps = load_episodes("src")
    assert eps == []


def test_index_paths_by_guid_skips_missing(tmp_path):
    """CR senior C1 — un payload sans guid valide n'est PAS indexé sous
    la clé chaîne vide.
    """
    p1 = tmp_path / "ok.json"
    p2 = tmp_path / "no_guid.json"
    idx = index_paths_by_guid([(p1, {"guid": "g1"}), (p2, {"foo": "bar"})])
    assert idx == {"g1": p1}


def test_index_paths_by_guid_skips_empty_string():
    p = Path("/tmp/x.json")
    idx = index_paths_by_guid([(p, {"guid": ""})])
    assert idx == {}


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


def _report_with_findings(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    _make_ep(src, "g1", 3600, 5400)  # suspect
    _make_ep(src, "g2", 3600, 3700, "abc", "abc x")  # clean
    svc = default_service("src", base_transcripts_dir=tmp_path / "t")
    eps = load_episodes("src")
    return svc.audit_source("src", [ep for _, ep in eps])


def test_format_json_contains_counts(tmp_path, monkeypatch):
    report = _report_with_findings(monkeypatch, tmp_path)
    out = json.loads(format_json(report))
    assert out["source_id"] == "src"
    assert out["suspect_count"] == 1
    assert out["audited_count"] == 2
    assert "clean_count" in out
    assert "skipped_no_guid" in out


def test_format_markdown_escapes_pipes(tmp_path):
    """CR senior H7 — un guid contenant `|` doit être échappé en
    Markdown (\\|). On construit le rapport directement (sans I/O) pour
    pouvoir tester un guid problématique sur Windows.
    """
    from tools.match_audit.service import MatchAuditResult, SourceAuditReport
    from tools.match_audit.types import MatchSuspicion, Severity
    susp = MatchSuspicion(
        kind="duration_mismatch", detail="diff|big", severity=Severity.ERROR,
    )
    r = MatchAuditResult(
        episode_guid="pipe|guid", is_suspect=True, suspicions=(susp,),
    )
    report = SourceAuditReport(source_id="my|src", total=1, results=(r,))
    md = format_markdown(report)
    assert "pipe\\|guid" in md
    assert "my\\|src" in md
    assert "diff\\|big" in md


def test_format_markdown_empty_says_aucun(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    _make_ep(src, "g1", 3600, 3700, "abc", "abc x")  # clean
    svc = default_service("src", base_transcripts_dir=tmp_path / "t")
    eps = load_episodes("src")
    report = svc.audit_source("src", [ep for _, ep in eps])
    md = format_markdown(report)
    assert "Aucun" in md


def test_format_human_one_line_per_finding(tmp_path, monkeypatch):
    report = _report_with_findings(monkeypatch, tmp_path)
    out = format_human(report)
    assert "audités=2" in out
    assert "suspects=1" in out
    assert "g1" in out


def test_report_as_dict_includes_audited_guids(tmp_path, monkeypatch):
    report = _report_with_findings(monkeypatch, tmp_path)
    d = report_as_dict(report)
    assert d["audited_episode_guids"] == ["g1", "g2"]


# ---------------------------------------------------------------------------
# emit_jsonl_events (CR senior H6)
# ---------------------------------------------------------------------------


def test_emit_jsonl_writes_one_event_per_finding(tmp_path, monkeypatch):
    report = _report_with_findings(monkeypatch, tmp_path)
    sink = io.StringIO()
    emit_jsonl_events(report, sink=sink)
    lines = [json.loads(line) for line in sink.getvalue().splitlines() if line.strip()]
    assert all(ev["event"] == "match_audit.finding" for ev in lines)
    assert any(ev["episode_guid"] == "g1" for ev in lines)


# ---------------------------------------------------------------------------
# run_audit
# ---------------------------------------------------------------------------


def test_run_audit_check_mode_does_not_modify(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    p = _make_ep(src, "g1", 3600, 5400)
    opts = RunOptions(
        source_id="src", mode="check",
        sidecar_base_dir=tmp_path / "out",
        base_transcripts_dir=tmp_path / "t",
    )
    res = run_audit(opts)
    assert res.exit_code == 0
    assert res.files_changed == 0
    assert res.sidecars_written == 0
    assert "matchSuspect" not in json.loads(p.read_text(encoding="utf-8"))


def test_run_audit_apply_writes_flag_and_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    p = _make_ep(src, "g1", 3600, 5400)
    opts = RunOptions(
        source_id="src", mode="apply",
        sidecar_base_dir=tmp_path / "out",
        base_transcripts_dir=tmp_path / "t",
    )
    res = run_audit(opts)
    assert res.files_changed == 1
    assert res.sidecars_written == 1
    assert json.loads(p.read_text(encoding="utf-8"))["matchSuspect"] is True
    assert res.trail_path is not None and res.trail_path.exists()


def test_run_audit_apply_idempotent_second_call_no_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    _make_ep(src, "g1", 3600, 5400)
    opts = RunOptions(
        source_id="src", mode="apply",
        sidecar_base_dir=tmp_path / "out",
        base_transcripts_dir=tmp_path / "t",
    )
    res1 = run_audit(opts)
    assert res1.files_changed == 1
    res2 = run_audit(opts)
    assert res2.files_changed == 0  # idempotent


def test_run_audit_fail_on_suspect_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    _make_ep(src, "g1", 3600, 5400)
    opts = RunOptions(
        source_id="src", mode="check", fail_on_suspect=True,
        sidecar_base_dir=tmp_path / "out",
        base_transcripts_dir=tmp_path / "t",
    )
    assert run_audit(opts).exit_code == 1


def test_run_audit_apply_clean_skips_sidecar(tmp_path, monkeypatch):
    """Pas de sidecar pour les épisodes clean (évite la pollution)."""
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    _make_ep(src, "g1", 3600, 3700, "abc", "abc x")  # clean
    opts = RunOptions(
        source_id="src", mode="apply",
        sidecar_base_dir=tmp_path / "out",
        base_transcripts_dir=tmp_path / "t",
    )
    res = run_audit(opts)
    assert res.sidecars_written == 0


def test_run_audit_format_json_returns_json_text(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    _make_ep(src, "g1", 3600, 5400)
    opts = RunOptions(
        source_id="src", mode="check", output_format="json",
        sidecar_base_dir=tmp_path / "out",
        base_transcripts_dir=tmp_path / "t",
    )
    res = run_audit(opts)
    json.loads(res.output_text)  # must parse


def test_run_audit_apply_skips_orphan_results(tmp_path, monkeypatch):
    """Si un result n'a pas de chemin (orphelin), on skip sans crasher
    (couvre la branche `paths_by_guid.get(...) is None`)."""
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    _make_ep(src, "g1", 3600, 5400)  # suspect, sera flagué

    # On force un service qui ajoute un résultat "ghost" sans path en
    # patchant la méthode audit_source.
    from tools.match_audit.service import (
        MatchAuditResult,
        SourceAuditReport,
    )
    from tools.match_audit.types import MatchSuspicion, Severity
    susp = MatchSuspicion(kind="duration_mismatch", detail="x",
                          severity=Severity.ERROR)
    real_default = default_service

    def fake_default(source_id, **kw):
        svc = real_default(source_id, **kw)

        def fake_audit_source(sid, eps):
            return SourceAuditReport(
                source_id=sid, total=1,
                results=(MatchAuditResult(
                    episode_guid="orphan",
                    is_suspect=True,
                    suspicions=(susp,),
                ),),
            )
        svc.audit_source = fake_audit_source  # type: ignore[method-assign]
        return svc

    from tools.match_audit import cli_runner as cr
    monkeypatch.setattr(cr, "default_service", fake_default)

    opts = RunOptions(
        source_id="src", mode="apply",
        sidecar_base_dir=tmp_path / "out",
        base_transcripts_dir=tmp_path / "t",
    )
    res = run_audit(opts)
    assert res.files_changed == 0  # le ghost n'a pas de path → skip
    assert res.sidecars_written == 1  # mais on a écrit son sidecar


def test_run_audit_format_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    _make_ep(src, "g1", 3600, 5400)
    opts = RunOptions(
        source_id="src", mode="check", output_format="markdown",
        sidecar_base_dir=tmp_path / "out",
        base_transcripts_dir=tmp_path / "t",
    )
    res = run_audit(opts)
    assert res.output_text.startswith("# Audit match")


# ---------------------------------------------------------------------------
# undo_last_apply
# ---------------------------------------------------------------------------


def test_undo_last_apply_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    p = _make_ep(src, "g1", 3600, 5400)
    base = tmp_path / "out"
    opts = RunOptions(
        source_id="src", mode="apply",
        sidecar_base_dir=base,
        base_transcripts_dir=tmp_path / "t",
    )
    run_audit(opts)
    assert json.loads(p.read_text(encoding="utf-8"))["matchSuspect"] is True
    res = undo_last_apply("src", sidecar_base_dir=base)
    assert res["flags_cleared"] == 1
    assert res["sidecars_deleted"] == 1
    assert "matchSuspect" not in json.loads(p.read_text(encoding="utf-8"))


def test_undo_last_apply_no_dir(tmp_path):
    res = undo_last_apply("src", sidecar_base_dir=tmp_path / "ghost")
    assert res["flags_cleared"] == 0
    assert res["sidecars_deleted"] == 0


def test_undo_last_apply_no_trail(tmp_path):
    (tmp_path / "src").mkdir()
    res = undo_last_apply("src", sidecar_base_dir=tmp_path)
    assert res["flags_cleared"] == 0
    assert res["sidecars_deleted"] == 0


def test_trail_path_for_run_is_deterministic_with_ts(tmp_path):
    p = trail_path_for_run("src", base_dir=tmp_path, timestamp="2026-06-10T00:00:00Z")
    assert p.name == "_run_20260610T000000Z.jsonl"


def test_undo_last_handles_missing_file_event(tmp_path, monkeypatch):
    """Si un event pointe vers un fichier déjà supprimé, on n'incrémente pas."""
    base = tmp_path / "out"
    d = base / "src"
    d.mkdir(parents=True)
    trail = d / "_run_20260610T000000Z.jsonl"
    trail.write_text(json.dumps({
        "event": "match_audit.flag", "path": str(d / "ghost.json"),
        "changed": True, "suspect": True,
    }) + "\n" + json.dumps({
        "event": "match_audit.sidecar", "sidecar": str(d / "ghost.json"),
    }) + "\n", encoding="utf-8")
    res = undo_last_apply("src", sidecar_base_dir=base)
    assert res["flags_cleared"] == 0
    assert res["sidecars_deleted"] == 0
