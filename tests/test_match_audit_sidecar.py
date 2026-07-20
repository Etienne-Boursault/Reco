"""Tests : tools.match_audit.sidecar."""
from __future__ import annotations

import json

import pytest

from tools.match_audit.service import MatchAuditResult
from tools.match_audit.sidecar import (
    delete_sidecar,
    iter_sidecars,
    list_sidecars,
    read_sidecar,
    sidecar_dir_for,
    sidecar_path,
    write_sidecar,
)
from tools.match_audit.types import MatchSuspicion, Severity


def _result(guid: str = "g1", suspect: bool = True) -> MatchAuditResult:
    susps = (
        MatchSuspicion(kind="duration_mismatch", detail="d",
                       severity=Severity.ERROR),
    ) if suspect else ()
    return MatchAuditResult(
        episode_guid=guid, is_suspect=suspect, suspicions=susps,
    )


# ---------------------------------------------------------------------------
# sidecar_path
# ---------------------------------------------------------------------------


def test_path_uses_base_dir(tmp_path):
    p = sidecar_path("src", "abc", base_dir=tmp_path)
    assert p.parent == tmp_path / "src"
    assert p.name.endswith(".json")


def test_path_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        sidecar_path("../escape", "g", base_dir=tmp_path)
    with pytest.raises(ValueError):
        sidecar_path("src", "../escape", base_dir=tmp_path)
    with pytest.raises(ValueError):
        sidecar_path("src/sub", "g", base_dir=tmp_path)


def test_path_rejects_empty(tmp_path):
    with pytest.raises(ValueError):
        sidecar_path("", "g", base_dir=tmp_path)
    with pytest.raises(ValueError):
        sidecar_path("src", "", base_dir=tmp_path)


def test_sidecar_dir_for_uses_base_dir(tmp_path):
    assert sidecar_dir_for("src", base_dir=tmp_path) == tmp_path / "src"


def test_sidecar_dir_for_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        sidecar_dir_for("../x", base_dir=tmp_path)


# ---------------------------------------------------------------------------
# write_sidecar
# ---------------------------------------------------------------------------


def test_write_sidecar_serializes_suspicions(tmp_path):
    res = _result()
    p = write_sidecar(res, "src", base_dir=tmp_path, audited_at="2026-06-10T00:00:00Z")
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["episodeGuid"] == "g1"
    assert payload["matchSuspect"] is True
    assert payload["suspicions"][0]["kind"] == "duration_mismatch"
    assert payload["suspicions"][0]["severity"] == "error"
    assert payload["auditedAt"] == "2026-06-10T00:00:00Z"


def test_write_sidecar_clean_result(tmp_path):
    res = _result(suspect=False)
    p = write_sidecar(res, "src", base_dir=tmp_path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["matchSuspect"] is False
    assert payload["suspicions"] == []


def test_write_sidecar_default_audited_at_iso(tmp_path):
    res = _result()
    p = write_sidecar(res, "src", base_dir=tmp_path)
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["auditedAt"].endswith("Z")


# ---------------------------------------------------------------------------
# read / list / iter / delete
# ---------------------------------------------------------------------------


def test_read_sidecar_round_trip(tmp_path):
    res = _result()
    write_sidecar(res, "src", base_dir=tmp_path)
    raw = read_sidecar("src", "g1", base_dir=tmp_path)
    assert raw is not None
    assert raw["matchSuspect"] is True


def test_read_sidecar_missing_returns_none(tmp_path):
    assert read_sidecar("src", "ghost", base_dir=tmp_path) is None


def test_read_sidecar_bad_json_returns_none(tmp_path):
    p = sidecar_path("src", "g", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not-json", encoding="utf-8")
    assert read_sidecar("src", "g", base_dir=tmp_path) is None


def test_read_sidecar_non_dict_returns_none(tmp_path):
    p = sidecar_path("src", "g", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1,2]", encoding="utf-8")
    assert read_sidecar("src", "g", base_dir=tmp_path) is None


def test_list_sidecars_returns_sorted(tmp_path):
    for g in ("c", "a", "b"):
        write_sidecar(_result(guid=g), "src", base_dir=tmp_path)
    paths = list_sidecars("src", base_dir=tmp_path)
    assert [p.stem for p in paths] == sorted([p.stem for p in paths])


def test_list_sidecars_empty_when_dir_missing(tmp_path):
    assert list_sidecars("ghost", base_dir=tmp_path) == []


def test_iter_sidecars_yields_payloads(tmp_path):
    write_sidecar(_result("a"), "src", base_dir=tmp_path)
    write_sidecar(_result("b"), "src", base_dir=tmp_path)
    payloads = list(iter_sidecars("src", base_dir=tmp_path))
    guids = {p["episodeGuid"] for p in payloads}
    assert guids == {"a", "b"}


def test_iter_sidecars_skips_bad_json(tmp_path):
    write_sidecar(_result("ok"), "src", base_dir=tmp_path)
    bad = sidecar_path("src", "bad", base_dir=tmp_path)
    bad.write_text("nope", encoding="utf-8")
    payloads = list(iter_sidecars("src", base_dir=tmp_path))
    assert {p["episodeGuid"] for p in payloads} == {"ok"}


def test_delete_sidecar_removes_file(tmp_path):
    write_sidecar(_result(), "src", base_dir=tmp_path)
    assert delete_sidecar("src", "g1", base_dir=tmp_path) is True
    assert delete_sidecar("src", "g1", base_dir=tmp_path) is False
