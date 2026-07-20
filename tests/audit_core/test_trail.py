"""Tests audit_core.trail — JsonlAuditTrail, NoopAuditTrail."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from audit_core.trail import AuditTrail, JsonlAuditTrail, NoopAuditTrail


class TestNoopAuditTrail:
    def test_record_returns_none(self) -> None:
        trail = NoopAuditTrail()
        assert trail.record({"event": "x"}) is None

    def test_conforms_to_audit_trail_protocol(self) -> None:
        assert isinstance(NoopAuditTrail(), AuditTrail)


class TestJsonlAuditTrail:
    def test_record_creates_parents(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "trail.jsonl"
        trail = JsonlAuditTrail(path)
        trail.record({"event": "x", "v": 1})
        assert path.exists()

    def test_record_jsonl_format(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        trail = JsonlAuditTrail(path)
        trail.record({"event": "a", "n": 1})
        trail.record({"event": "b", "n": 2})
        content = path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "a"
        assert json.loads(lines[1])["n"] == 2

    def test_record_sort_keys(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        trail = JsonlAuditTrail(path)
        trail.record({"z": 1, "a": 2})
        line = path.read_text(encoding="utf-8").strip()
        # sort_keys=True => 'a' avant 'z'
        assert line.index('"a"') < line.index('"z"')

    def test_iter_events_empty_if_no_file(self, tmp_path: Path) -> None:
        path = tmp_path / "absent.jsonl"
        trail = JsonlAuditTrail(path)
        assert list(trail.iter_events()) == []

    def test_iter_events_yields_dicts(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        trail = JsonlAuditTrail(path)
        trail.record({"event": "a"})
        trail.record({"event": "b"})
        events = list(trail.iter_events())
        assert [e["event"] for e in events] == ["a", "b"]

    def test_iter_events_skips_blank_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            '{"event":"a"}\n\n   \n{"event":"b"}\n',
            encoding="utf-8",
        )
        trail = JsonlAuditTrail(path)
        assert [e["event"] for e in trail.iter_events()] == ["a", "b"]

    def test_iter_events_skips_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            '{"event":"a"}\nnot-json\n{"event":"b"}\n',
            encoding="utf-8",
        )
        trail = JsonlAuditTrail(path)
        assert [e["event"] for e in trail.iter_events()] == ["a", "b"]

    def test_iter_events_skips_non_dict(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            '{"event":"a"}\n[1,2,3]\n{"event":"b"}\n',
            encoding="utf-8",
        )
        trail = JsonlAuditTrail(path)
        assert [e["event"] for e in trail.iter_events()] == ["a", "b"]

    def test_path_property(self, tmp_path: Path) -> None:
        p = tmp_path / "t.jsonl"
        assert JsonlAuditTrail(p).path == p

    def test_conforms_to_audit_trail_protocol(self, tmp_path: Path) -> None:
        assert isinstance(JsonlAuditTrail(tmp_path / "x.jsonl"), AuditTrail)
