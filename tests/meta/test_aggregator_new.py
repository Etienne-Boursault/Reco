"""Tests Phase-4 fixer pour `tools/meta/aggregator.py`."""
from __future__ import annotations

import logging

import pytest

from meta.aggregator import (
    _sort_key_title,
    aggregate_entries,
    dedupe_by_slug,
    slug_from_site_url,
)
from meta import aggregator as _agg


def test_slug_triple_dash_input() -> None:
    """B-LOW-2 — '---' (que des séparateurs) doit donner 'unknown'."""
    assert slug_from_site_url("---") == "unknown"


def test_dedupe_logs_warning_on_duplicate(caplog: pytest.LogCaptureFixture) -> None:
    """B-MED-10 — slug dup → log.warning."""
    caplog.set_level(logging.WARNING, logger=_agg.__name__)
    out = dedupe_by_slug(
        [
            {"slug": "a", "sourceUrl": "u1"},
            {"slug": "a", "sourceUrl": "u2"},
        ],
    )
    assert len(out) == 1
    assert any("déjà vu" in rec.message for rec in caplog.records)


def test_aggregate_missing_stats_keys_uses_zero() -> None:
    """B-MED-11 — stats absentes → comptés comme 0, pas KeyError."""
    items = [
        {
            "sourceUrl": "u1",
            "registry": {
                "siteUrl": "https://x.example",
                "podcast": {"title": "X"},
                "stats": {},  # toutes les clés manquantes
            },
        }
    ]
    out = aggregate_entries(items)
    assert out["totals"]["mentions"] == 0
    assert out["totals"]["items"] == 0


def test_aggregate_no_stats_dict_uses_zero() -> None:
    """B-MED-11 — clé `stats` absente totalement → 0."""
    items = [
        {
            "sourceUrl": "u1",
            "registry": {
                "siteUrl": "https://x.example",
                "podcast": {"title": "X"},
            },
        }
    ]
    out = aggregate_entries(items)
    assert out["totals"]["mentions"] == 0


def test_sort_key_title_strips_combining_marks() -> None:
    """B-LOW-3 — NFKD + strip combining → 'Étoile' == 'Etoile' pour le tri."""
    a = _sort_key_title("Étoile")
    b = _sort_key_title("Etoile")
    assert a == b


def test_aggregate_param_name_is_entries_in() -> None:
    """B-NIT-3 — paramètre renommé : `entries_in` (pas `items`)."""
    import inspect
    sig = inspect.signature(aggregate_entries)
    assert "entries_in" in sig.parameters


def test_dedupe_skips_non_string_slug(caplog: pytest.LogCaptureFixture) -> None:
    """Slug non-str → drop SANS log (ce n'est pas un 'duplicate')."""
    caplog.set_level(logging.WARNING, logger=_agg.__name__)
    out = dedupe_by_slug([{"slug": 42}])
    assert out == []
    assert all("déjà vu" not in rec.message for rec in caplog.records)
