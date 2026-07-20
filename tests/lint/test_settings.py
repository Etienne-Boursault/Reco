"""Tests TDD pour `LintSettings` (CR archi #2/#5)."""
from __future__ import annotations

from datetime import date

import pytest

from lint.settings import (
    DEFAULT_TITLE_SUSPICIOUS_PATTERNS,
    DEFAULT_YEAR_MAX,
    DEFAULT_YEAR_MIN,
    LintSettings,
)


def test_defaults_are_sane():
    s = LintSettings()
    assert s.year_min == DEFAULT_YEAR_MIN
    assert s.year_max == DEFAULT_YEAR_MAX
    assert s.title_min_len > 0
    assert s.title_suspicious_patterns == DEFAULT_TITLE_SUSPICIOUS_PATTERNS
    assert isinstance(s.today, date)


def test_rejects_year_min_greater_than_max():
    with pytest.raises(ValueError):
        LintSettings(year_min=2100, year_max=1800)


def test_rejects_negative_lengths():
    with pytest.raises(ValueError):
        LintSettings(title_min_len=0)
    with pytest.raises(ValueError):
        LintSettings(title_min_len=10, title_max_len=5)


def test_rejects_non_tuple_patterns():
    with pytest.raises(ValueError):
        LintSettings(title_suspicious_patterns=["x"])  # type: ignore[arg-type]


def test_rejects_pattern_non_str():
    with pytest.raises(ValueError):
        LintSettings(title_suspicious_patterns=(1,))  # type: ignore[arg-type]


def test_rejects_non_int_thresholds():
    with pytest.raises(ValueError):
        LintSettings(year_min="1800")  # type: ignore[arg-type]


def test_rejects_invalid_enabled_rules_type():
    with pytest.raises(ValueError):
        LintSettings(enabled_rules=["a"])  # type: ignore[arg-type]


def test_rejects_invalid_disabled_rules_type():
    with pytest.raises(ValueError):
        LintSettings(disabled_rules=["a"])  # type: ignore[arg-type]


def test_rejects_today_not_date():
    with pytest.raises(ValueError):
        LintSettings(today="2026-06-10")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# from_source_extra
# ---------------------------------------------------------------------------


def test_from_source_extra_none_returns_defaults():
    s = LintSettings.from_source_extra(None)
    assert s.year_min == DEFAULT_YEAR_MIN


def test_from_source_extra_missing_lint_key_returns_defaults():
    s = LintSettings.from_source_extra({"foo": "bar"})
    assert s.year_min == DEFAULT_YEAR_MIN


def test_from_source_extra_reads_lint_subkey():
    s = LintSettings.from_source_extra({
        "lint": {
            "year_min": 1900, "year_max": 2050,
            "title_min_len": 5, "title_max_len": 80,
            "title_caps_threshold": 8,
            "title_suspicious_patterns": [r"\(extra\)"],
            "enabled_rules": ["required_fields", "aberrant_values"],
            "disabled_rules": ["suspicious_titles"],
        }
    })
    assert s.year_min == 1900
    assert s.year_max == 2050
    assert s.title_min_len == 5
    assert s.title_suspicious_patterns == (r"\(extra\)",)
    assert s.enabled_rules == ("required_fields", "aberrant_values")
    assert s.disabled_rules == ("suspicious_titles",)


def test_from_source_extra_overrides_win_over_extra():
    s = LintSettings.from_source_extra(
        {"lint": {"year_min": 1900}},
        overrides={"year_min": 1950},
    )
    assert s.year_min == 1950


def test_from_source_extra_ignores_null_values():
    s = LintSettings.from_source_extra({"lint": {"year_min": None}})
    assert s.year_min == DEFAULT_YEAR_MIN


# ---------------------------------------------------------------------------
# is_rule_enabled
# ---------------------------------------------------------------------------


def test_is_rule_enabled_default_all():
    s = LintSettings()
    assert s.is_rule_enabled("any_rule") is True


def test_disabled_rules_take_precedence():
    s = LintSettings(disabled_rules=("required_fields",))
    assert s.is_rule_enabled("required_fields") is False


def test_enabled_rules_whitelist():
    s = LintSettings(enabled_rules=("required_fields",))
    assert s.is_rule_enabled("required_fields") is True
    assert s.is_rule_enabled("aberrant_values") is False


def test_disabled_wins_over_enabled():
    s = LintSettings(
        enabled_rules=("required_fields",),
        disabled_rules=("required_fields",),
    )
    assert s.is_rule_enabled("required_fields") is False
