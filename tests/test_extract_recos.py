"""Tests des helpers de normalisation et dédoublonnage de recos
(tools/extract_recos.py).

On teste les briques pures (sans appel LLM) : `_norm` et `_dedupe`.
"""
from __future__ import annotations

from extract_recos import _dedupe, _norm


# ===== _norm ==============================================================
def test_norm_strips_accents_case_punct():
    """Mortel, MORTEL, mortél et 'mortel.' doivent tous donner la même clé."""
    expected = _norm("Mortel")
    assert _norm("MORTEL") == expected
    assert _norm("mortél") == expected
    assert _norm("mortel.") == expected


def test_norm_collapses_whitespace():
    assert _norm("Full   Metal   Jacket") == _norm("Full Metal Jacket")


def test_norm_empty_or_none():
    assert _norm("") == ""
    assert _norm(None) == ""


def test_norm_keeps_digits():
    assert "2001" in _norm("2001 : l'Odyssée de l'espace")


# ===== _dedupe ============================================================
def test_dedupe_collapses_duplicate_titles():
    recos = [
        {"title": "Mortel", "creator": None},
        {"title": "MORTEL", "creator": "Frédéric Garcia"},  # même clé après _norm
    ]
    out = _dedupe(recos)
    assert len(out) == 1
    # Le 1er gagne mais on enrichit avec les champs manquants depuis les suivants.
    assert out[0]["creator"] == "Frédéric Garcia"


def test_dedupe_keeps_distinct_titles():
    recos = [
        {"title": "Mortel"},
        {"title": "Full Metal Jacket"},
    ]
    out = _dedupe(recos)
    assert len(out) == 2


def test_dedupe_merges_missing_fields():
    recos = [
        {"title": "Hozier", "creator": None, "year": None,        "timestamp": "00:42:11"},
        {"title": "hozier", "creator": "Andrew Hozier-Byrne", "year": 2014, "timestamp": None},
    ]
    out = _dedupe(recos)
    assert len(out) == 1
    merged = out[0]
    assert merged["creator"] == "Andrew Hozier-Byrne"
    assert merged["year"] == 2014
    # Le timestamp du 1er est préservé (n'est pas écrasé puisqu'il était déjà rempli).
    assert merged["timestamp"] == "00:42:11"


def test_dedupe_preserves_first_when_both_have_field():
    """Si les deux ont la même clé _norm et que le champ existe déjà dans le 1er,
    on ne l'écrase pas avec celui du suivant."""
    recos = [
        {"title": "Mortel", "creator": "Frédéric Garcia"},
        {"title": "Mortel", "creator": "Autre Créateur"},
    ]
    out = _dedupe(recos)
    assert len(out) == 1
    assert out[0]["creator"] == "Frédéric Garcia"
