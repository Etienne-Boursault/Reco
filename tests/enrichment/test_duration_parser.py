"""Tests de `enrichment.duration.parse_duration`."""
from __future__ import annotations

from datetime import timedelta

import pytest

from enrichment.duration import parse_duration


@pytest.mark.parametrize(
    "value,expected",
    [
        ("30d", timedelta(days=30)),
        ("0d", timedelta(0)),
        ("1d", timedelta(days=1)),
        ("12w", timedelta(days=12 * 7)),
        ("6m", timedelta(days=6 * 30)),
        ("2y", timedelta(days=2 * 365)),
        ("48h", timedelta(hours=48)),
        ("  90d  ", timedelta(days=90)),  # tolère espaces
        ("90D", timedelta(days=90)),  # tolère majuscules
    ],
)
def test_parse_valid(value, expected):
    assert parse_duration(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "30",  # pas d'unité
        "d",  # pas de nombre
        "-5d",  # négatif rejeté
        "5days",  # mot complet pas accepté
        "5x",  # unité inconnue
        "1.5d",  # flottant rejeté
        None,  # type invalide
        123,  # type invalide
    ],
)
def test_parse_invalid(value):
    with pytest.raises(ValueError):
        parse_duration(value)  # type: ignore[arg-type]
