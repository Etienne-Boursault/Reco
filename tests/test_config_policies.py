"""Tests des politiques projet (constantes éditoriales)."""

from __future__ import annotations

from tools.config.policies import PROJECT_AVOID_BRANDS


def test_project_avoid_brands_is_immutable_tuple():
    assert isinstance(PROJECT_AVOID_BRANDS, tuple)


def test_project_avoid_brands_contains_known_entries():
    """Cf. memory ``reco-liens-ethiques.md`` — au moins Amazon + Bolloré."""
    assert "Amazon" in PROJECT_AVOID_BRANDS
    assert "Bolloré" in PROJECT_AVOID_BRANDS


def test_project_avoid_brands_entries_are_strings():
    assert all(isinstance(b, str) for b in PROJECT_AVOID_BRANDS)
