"""Tests : tools.match_audit.strategies."""
from __future__ import annotations

from tools.match_audit.strategies import SequenceMatcherStrategy


def test_sequence_matcher_identical_returns_one():
    s = SequenceMatcherStrategy()
    assert s.compare("abcdef", "abcdef") == 1.0


def test_sequence_matcher_disjoint_low_score():
    s = SequenceMatcherStrategy()
    assert s.compare("aaaa", "zzzz") < 0.5


def test_sequence_matcher_empty_returns_zero():
    s = SequenceMatcherStrategy()
    assert s.compare("", "abc") == 0.0
    assert s.compare("abc", "") == 0.0
    assert s.compare("", "") == 0.0


def test_strategy_is_immutable():
    s = SequenceMatcherStrategy()
    # frozen dataclass — sanity check
    import dataclasses
    assert dataclasses.is_dataclass(s)
