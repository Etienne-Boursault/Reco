"""Tests : tools.match_audit.settings."""
from __future__ import annotations

import pytest

from tools.match_audit.settings import MatchAuditSettings


def test_default_settings_values():
    s = MatchAuditSettings()
    assert s.duration_tolerance == 0.05
    assert s.intro_threshold == 0.4
    assert s.intro_chars == 500
    assert s.title_threshold == 0.3
    assert s.enabled_checks is None


def test_settings_rejects_out_of_bounds():
    with pytest.raises(ValueError):
        MatchAuditSettings(duration_tolerance=1.5)
    with pytest.raises(ValueError):
        MatchAuditSettings(intro_threshold=-0.1)


def test_settings_rejects_non_numeric():
    with pytest.raises(ValueError):
        MatchAuditSettings(duration_tolerance="0.5")  # type: ignore[arg-type]


def test_settings_rejects_zero_intro_chars():
    with pytest.raises(ValueError):
        MatchAuditSettings(intro_chars=0)


def test_settings_rejects_non_int_intro_chars():
    with pytest.raises(ValueError):
        MatchAuditSettings(intro_chars=3.5)  # type: ignore[arg-type]


def test_settings_rejects_bool_as_int():
    """bool est un int en Python — on doit l'écarter explicitement."""
    with pytest.raises(ValueError):
        MatchAuditSettings(intro_chars=True)  # type: ignore[arg-type]


def test_settings_rejects_list_enabled_checks():
    """enabled_checks doit être un tuple immuable."""
    with pytest.raises(ValueError):
        MatchAuditSettings(enabled_checks=["duration_mismatch"])  # type: ignore[arg-type]


def test_from_source_extra_uses_payload_values():
    extra = {
        "match_audit": {
            "duration_tolerance": 0.10,
            "intro_threshold": 0.6,
            "title_threshold": 0.5,
            "intro_chars": 1000,
            "enabled_checks": ["duration_mismatch"],
        },
    }
    s = MatchAuditSettings.from_source_extra(extra)
    assert s.duration_tolerance == 0.10
    assert s.intro_threshold == 0.6
    assert s.title_threshold == 0.5
    assert s.intro_chars == 1000
    assert s.enabled_checks == ("duration_mismatch",)


def test_from_source_extra_overrides_win():
    extra = {"match_audit": {"duration_tolerance": 0.10}}
    s = MatchAuditSettings.from_source_extra(
        extra, overrides={"duration_tolerance": 0.20},
    )
    assert s.duration_tolerance == 0.20


def test_from_source_extra_no_payload_uses_defaults():
    s = MatchAuditSettings.from_source_extra({})
    assert s.duration_tolerance == 0.05


def test_from_source_extra_none_extra():
    s = MatchAuditSettings.from_source_extra(None)
    assert s.duration_tolerance == 0.05


def test_from_source_extra_ignores_unknown_keys():
    extra = {"match_audit": {"unknown": 42, "duration_tolerance": 0.1}}
    s = MatchAuditSettings.from_source_extra(extra)
    assert s.duration_tolerance == 0.1


def test_from_source_extra_skips_none_overrides():
    s = MatchAuditSettings.from_source_extra(
        None, overrides={"duration_tolerance": None},
    )
    assert s.duration_tolerance == 0.05


def test_from_source_extra_non_mapping_payload_ignored():
    """Si extra["match_audit"] n'est pas un mapping → on garde les défauts."""
    s = MatchAuditSettings.from_source_extra({"match_audit": "garbage"})
    assert s.duration_tolerance == 0.05
