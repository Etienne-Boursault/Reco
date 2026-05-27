"""Tests du formatage de l'inventaire (tools/inventory_md.py)."""
from __future__ import annotations

from inventory_md import fmt_dur


def test_fmt_dur_zero_returns_dash():
    assert fmt_dur(0) == "—"
    assert fmt_dur(None) == "—"


def test_fmt_dur_under_a_minute():
    assert fmt_dur(45) == "0mn45"


def test_fmt_dur_exact_minute():
    assert fmt_dur(60) == "1mn00"


def test_fmt_dur_typical_episode():
    # 1h30m05 = 5405 secondes
    assert fmt_dur(5405) == "90mn05"


def test_fmt_dur_pads_seconds_to_two_digits():
    """Les secondes sont toujours sur 2 chiffres (« 5mn05 », pas « 5mn5 »)."""
    assert fmt_dur(305) == "5mn05"
