"""Test golden cross-stack (R-P1-23, M26-21) — Python side.

Consomme la fixture commune ``tests/fixtures/stats/golden/{input,snapshot}.json``
qui sert également au pendant TS (``test_golden.test.ts``).

But : si TS et Py convergent vers ce fichier, la parité d'exécution
``buildStatsSnapshot`` ≡ ``build_snapshot`` est garantie.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stats import build_snapshot

_FIXT = Path(__file__).parent.parent / "fixtures" / "stats" / "golden"


@pytest.fixture
def golden() -> tuple[dict, dict]:
    inp = json.loads((_FIXT / "input.json").read_text(encoding="utf-8"))
    exp = json.loads((_FIXT / "snapshot.json").read_text(encoding="utf-8"))
    return inp, exp


def test_golden_matches_python_snapshot(golden):
    inp, expected = golden
    snap = build_snapshot(
        sources=inp["sources"],
        episodes=inp["episodes"],
        mentions=inp["mentions"],
        items=inp["items"],
        generated_at=inp["generatedAt"],
    )
    payload = snap.to_dict()
    assert payload == expected


def test_golden_oeuvre_ligature_order(golden):
    """M26-21 : Œ ne décompose pas en NFKD ; OEuvre précède Œuvre."""
    _, expected = golden
    ones = [w["title"] for w in expected["topWorks"] if w["mentionsCount"] == 1]
    assert ones == ["OEuvre", "Œuvre"]


def test_golden_slug_collision_suffix(golden):
    _, expected = golden
    slugs = [g["slug"] for g in expected["topGuests"]]
    assert "lea-martin" in slugs
    assert "lea-martin-2" in slugs


def test_golden_monthly_fills_gaps(golden):
    _, expected = golden
    months = [b["month"] for b in expected["monthlyEpisodes"]]
    assert months == ["2024-01", "2024-02", "2024-03"]
