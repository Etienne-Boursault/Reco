"""Tests de `enrichment.field_refresher`."""
from __future__ import annotations

import pytest

from enrichment import EnrichedAtCorruptedError
from enrichment.field_refresher import partial_update, update_nested


def test_updates_field_and_traces_timestamp():
    item = {"id": "x", "year": 2019, "runtime": 132,
            "watchProviders": [{"label": "Netflix"}]}
    partial_update(item, "runtime", 135, timestamp="2026-06-10T12:00:00Z")
    assert item["runtime"] == 135
    # Champs non touchés préservés
    assert item["year"] == 2019
    assert item["watchProviders"] == [{"label": "Netflix"}]
    assert item["enrichedAt"] == {"runtime": "2026-06-10T12:00:00Z"}


def test_preserves_existing_enrichedat_entries():
    item = {
        "id": "x",
        "year": 2019,
        "enrichedAt": {"year": "2026-01-01T00:00:00Z"},
    }
    partial_update(item, "runtime", 132, timestamp="2026-06-10T12:00:00Z")
    assert item["enrichedAt"] == {
        "year": "2026-01-01T00:00:00Z",
        "runtime": "2026-06-10T12:00:00Z",
    }


def test_replaces_existing_field_timestamp():
    item = {
        "id": "x",
        "runtime": 130,
        "enrichedAt": {"runtime": "2026-01-01T00:00:00Z"},
    }
    partial_update(item, "runtime", 132, timestamp="2026-06-10T12:00:00Z")
    assert item["enrichedAt"]["runtime"] == "2026-06-10T12:00:00Z"


def test_default_timestamp_uses_now_iso():
    item = {"id": "x"}
    partial_update(item, "year", 2019)
    ts = item["enrichedAt"]["year"]
    assert ts.endswith("Z") and len(ts) == 20


def test_delete_if_none_removes_field_but_traces():
    item = {
        "id": "x",
        "watchProviders": [{"label": "Netflix"}],
        "enrichedAt": {"watchProviders": "2026-01-01T00:00:00Z"},
    }
    partial_update(
        item, "watchProviders", None,
        timestamp="2026-06-10T12:00:00Z", delete_if_none=True,
    )
    assert "watchProviders" not in item
    assert item["enrichedAt"]["watchProviders"] == "2026-06-10T12:00:00Z"


def test_none_without_delete_is_noop_on_value():
    item = {"id": "x", "runtime": 132}
    partial_update(
        item, "runtime", None,
        timestamp="2026-06-10T12:00:00Z", delete_if_none=False,
    )
    # Valeur conservée, mais on trace l'enrichissement.
    assert item["runtime"] == 132
    assert item["enrichedAt"]["runtime"] == "2026-06-10T12:00:00Z"


def test_partial_update_raises_on_corrupted_enrichedAt():
    """P0-5 : enrichedAt non-dict → EnrichedAtCorruptedError, jamais écrasé.

    Avant ce fix : la valeur corrompue était silencieusement remplacée par
    un dict vide → perte de tout audit trail. Désormais on lève pour que
    le caller (refresh_enrichment.run) skip l'item.
    """
    item = {"id": "x", "enrichedAt": "not-a-dict"}
    with pytest.raises(EnrichedAtCorruptedError):
        partial_update(item, "year", 2019, timestamp="2026-06-10T12:00:00Z")
    # L'item n'a pas été modifié — audit trail préservé pour inspection.
    assert item["enrichedAt"] == "not-a-dict"
    assert "year" not in item


def test_update_nested_raises_on_corrupted_enrichedAt():
    """P0-5 : même protection pour `update_nested`."""
    item = {"id": "x", "enrichedAt": 42}
    with pytest.raises(EnrichedAtCorruptedError):
        update_nested(item, "externalIds.tmdb", "1",
                      timestamp="2026-06-10T12:00:00Z")
    assert item["enrichedAt"] == 42
    assert "externalIds" not in item


def test_update_nested_creates_parents():
    item = {"id": "x"}
    update_nested(item, "externalIds.tmdb", "496243",
                  timestamp="2026-06-10T12:00:00Z")
    assert item["externalIds"] == {"tmdb": "496243"}
    assert item["enrichedAt"] == {"externalIds.tmdb": "2026-06-10T12:00:00Z"}


def test_update_nested_preserves_siblings():
    item = {
        "id": "x",
        "externalIds": {"tmdb": "496243", "imdb": "tt6751668"},
    }
    update_nested(item, "externalIds.tmdb", "999999",
                  timestamp="2026-06-10T12:00:00Z")
    assert item["externalIds"]["tmdb"] == "999999"
    assert item["externalIds"]["imdb"] == "tt6751668"


def test_update_nested_default_timestamp():
    item = {"id": "x"}
    update_nested(item, "externalIds.tmdb", "1")
    assert item["enrichedAt"]["externalIds.tmdb"].endswith("Z")


def test_update_nested_with_corrupt_parent_replaces_it():
    item = {"id": "x", "externalIds": "garbage"}
    update_nested(item, "externalIds.tmdb", "1",
                  timestamp="2026-06-10T12:00:00Z")
    assert item["externalIds"] == {"tmdb": "1"}
