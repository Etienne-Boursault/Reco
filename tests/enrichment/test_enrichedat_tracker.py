"""Tests de `enrichment.tracker`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from enrichment.tracker import EnrichedAtTracker, now_iso, stale_fields


NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)


def make(item_enrichedat: dict | None) -> dict:
    return {"id": "x", "title": "X", "enrichedAt": item_enrichedat} if item_enrichedat is not None else {"id": "x", "title": "X"}


def test_stale_when_missing_enrichedat():
    t = EnrichedAtTracker(older_than=timedelta(days=90), now=NOW)
    assert t.is_stale(make(None), "year") is True


def test_stale_when_field_absent():
    t = EnrichedAtTracker(older_than=timedelta(days=90), now=NOW)
    assert t.is_stale(make({"runtime": "2026-01-01T00:00:00Z"}), "year") is True


def test_fresh_when_recent():
    t = EnrichedAtTracker(older_than=timedelta(days=90), now=NOW)
    item = make({"year": "2026-06-01T00:00:00Z"})  # 9 jours
    assert t.is_stale(item, "year") is False


def test_stale_when_old_enough():
    t = EnrichedAtTracker(older_than=timedelta(days=90), now=NOW)
    item = make({"year": "2026-01-01T00:00:00Z"})  # ~160 jours
    assert t.is_stale(item, "year") is True


def test_stale_with_corrupt_timestamp():
    t = EnrichedAtTracker(older_than=timedelta(days=90), now=NOW)
    assert t.is_stale(make({"year": "pas-une-date"}), "year") is True


def test_zero_duration_forces_all_stale():
    t = EnrichedAtTracker(older_than=timedelta(0), now=NOW)
    item = make({"year": "2026-06-10T11:59:50Z"})  # 10s ago, mais older_than=0
    assert t.is_stale(item, "year") is True


def test_handles_plus_offset_timestamp():
    t = EnrichedAtTracker(older_than=timedelta(days=90), now=NOW)
    item = make({"year": "2026-06-01T00:00:00+00:00"})
    assert t.is_stale(item, "year") is False


def test_handles_naive_timestamp_as_utc():
    t = EnrichedAtTracker(older_than=timedelta(days=90), now=NOW)
    item = make({"year": "2026-06-01T00:00:00"})  # naive → UTC
    assert t.is_stale(item, "year") is False


def test_stale_fields_helper_preserves_order():
    item = make({
        "year": "2026-06-10T00:00:00Z",  # fresh
        "runtime": "2026-01-01T00:00:00Z",  # stale
    })
    result = stale_fields(
        item, ["year", "runtime", "providers_watch"],
        older_than=timedelta(days=90), now=NOW,
    )
    assert result == ["runtime", "providers_watch"]


def test_now_iso_format():
    s = now_iso()
    # Format strict : 2026-06-10T12:34:56Z
    assert len(s) == 20
    assert s.endswith("Z")
    assert s[10] == "T"
