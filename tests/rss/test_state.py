"""Tests rss.state : load/save JSON, atomicité, schemaVersion."""
from __future__ import annotations

import json
from pathlib import Path

from rss.state import (
    POLLING_STATE_SCHEMA_VERSION,
    PollingState,
    load_state,
    save_state,
    state_path_for,
)


def test_load_state_missing_file_returns_empty(tmp_path: Path):
    state = load_state("missing", state_dir=tmp_path)
    assert state.source_id == "missing"
    assert state.seen_guids == ()
    assert state.last_etag is None


def test_save_then_load_round_trip(tmp_path: Path):
    s = PollingState(
        source_id="x",
        last_checked_at="2026-06-12T00:00:00Z",
        last_etag="abc",
        last_modified="Wed, 11 Jun 2026 12:00:00 GMT",
        seen_guids=("g1", "g2"),
        metadata={"feedTitle": "T"},
    )
    save_state(s, state_dir=tmp_path)
    back = load_state("x", state_dir=tmp_path)
    assert back == s


def test_saved_file_has_schema_version(tmp_path: Path):
    save_state(PollingState(source_id="x"), state_dir=tmp_path)
    path = state_path_for("x", state_dir=tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == POLLING_STATE_SCHEMA_VERSION


def test_load_state_robust_to_corrupted_json(tmp_path: Path):
    path = state_path_for("x", state_dir=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")
    state = load_state("x", state_dir=tmp_path)
    # Renvoie un état vierge plutôt que de crasher.
    assert state.seen_guids == ()


def test_load_state_robust_to_non_dict_payload(tmp_path: Path):
    path = state_path_for("x", state_dir=tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("[]", encoding="utf-8")
    state = load_state("x", state_dir=tmp_path)
    assert state.source_id == "x"


def test_with_observed_appends_new_guids_mru_order(tmp_path: Path):
    s = PollingState(source_id="x", seen_guids=("g1",))
    s2 = s.with_observed(guids=["g3", "g2"], checked_at="t")
    # "g2" puis "g3" en queue (g3 plus récent du flux).
    assert s2.seen_guids == ("g1", "g2", "g3")
    assert s2.last_checked_at == "t"


def test_with_observed_idempotent_on_known_guids():
    s = PollingState(source_id="x", seen_guids=("g1", "g2"))
    s2 = s.with_observed(guids=["g1", "g2"], checked_at="t")
    assert s2.seen_guids == ("g1", "g2")


def test_with_observed_preserves_etag_when_not_provided():
    s = PollingState(source_id="x", last_etag="old")
    s2 = s.with_observed(guids=[], checked_at="t")
    assert s2.last_etag == "old"
    s3 = s.with_observed(guids=[], checked_at="t", etag="new")
    assert s3.last_etag == "new"
