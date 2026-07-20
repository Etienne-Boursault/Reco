"""Tests : tools.match_audit.audit_trail."""
from __future__ import annotations

import json

from tools.match_audit.audit_trail import JsonlAuditTrail, NoopAuditTrail


def test_noop_records_nothing(tmp_path):
    t = NoopAuditTrail()
    t.record({"any": "event"})  # ne lève pas, ne fait rien
    assert list(tmp_path.iterdir()) == []


def test_jsonl_appends_one_line_per_event(tmp_path):
    p = tmp_path / "trail.jsonl"
    t = JsonlAuditTrail(p)
    t.record({"event": "a", "v": 1})
    t.record({"event": "b", "v": 2})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "a"
    assert json.loads(lines[1])["event"] == "b"


def test_jsonl_creates_parents(tmp_path):
    p = tmp_path / "deep" / "trail.jsonl"
    JsonlAuditTrail(p).record({"k": 1})
    assert p.exists()


def test_iter_events_yields_dicts(tmp_path):
    p = tmp_path / "t.jsonl"
    t = JsonlAuditTrail(p)
    t.record({"i": 1})
    t.record({"i": 2})
    events = list(t.iter_events())
    assert [e["i"] for e in events] == [1, 2]


def test_iter_events_empty_when_missing(tmp_path):
    p = tmp_path / "missing.jsonl"
    assert list(JsonlAuditTrail(p).iter_events()) == []


def test_iter_events_skips_bad_lines(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"ok": 1}\nnot-json\n{"ok": 2}\n', encoding="utf-8")
    events = list(JsonlAuditTrail(p).iter_events())
    assert events == [{"ok": 1}, {"ok": 2}]


def test_jsonl_path_property(tmp_path):
    p = tmp_path / "t.jsonl"
    assert JsonlAuditTrail(p).path == p


def test_iter_events_skips_blank_and_non_dict(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('\n[1,2]\n{"ok":1}\n', encoding="utf-8")
    assert list(JsonlAuditTrail(p).iter_events()) == [{"ok": 1}]
