"""Tests TDD pour `AberrantValuesRule` (post-CR senior C1/H1/H2/M6)."""
from __future__ import annotations

from datetime import date

from lint.rules.aberrant_values import AberrantValuesRule
from lint.rules.base import LintContext, Severity
from lint.settings import LintSettings


def _ctx(recos):
    return LintContext(source_id="ubm", recos=tuple(recos))


# `today` injecté pour déterminisme (M9/M6).
_S = LintSettings(today=date(2026, 6, 10))


def _rule(*, known_types=None) -> AberrantValuesRule:
    # Évite la dépendance lazy à `domain.item.ItemType` dans les tests
    # micro (H2) — on injecte les types explicitement.
    return AberrantValuesRule(
        _S, known_types=known_types or frozenset({"film", "livre", "serie"}),
    )


def test_clean_reco_emits_nothing():
    rule = _rule()
    reco = {
        "id": "ubm-1", "title": "T", "year": 2020,
        "timestamp": "00:13:21", "types": ["film"],
    }
    assert list(rule.check(_ctx([reco]))) == []


def test_year_below_min_flagged():
    rule = _rule()
    reco = {"id": "ubm-2", "year": 1500, "types": ["film"]}
    issues = list(rule.check(_ctx([reco])))
    assert len(issues) == 1
    assert issues[0].field == "year"
    assert issues[0].severity == Severity.ERROR


def test_year_above_hard_max_flagged_error():
    rule = _rule()
    reco = {"id": "ubm-3", "year": 3000, "types": ["film"]}
    issues = list(rule.check(_ctx([reco])))
    assert {i.severity for i in issues if i.field == "year"} == {Severity.ERROR}


def test_year_at_soft_min_is_clean():
    rule = _rule()
    reco = {"id": "ubm-4", "year": 1800, "types": ["film"]}
    assert list(rule.check(_ctx([reco]))) == []


def test_year_at_soft_max_within_settings_is_clean():
    """Avec year_max=2100 et today=2026, year=2027 (=today+1) reste clean."""
    rule = _rule()
    reco = {"id": "ubm-soft", "year": 2027, "types": ["film"]}
    assert list(rule.check(_ctx([reco]))) == []


def test_year_in_future_beyond_soft_max_is_warning_not_error():
    """M6 : year>max(year_max, today+1) → WARNING (pas ERROR)."""
    # year_max=2030 + today=2026 → soft_max=max(2030, 2027) = 2030
    # year=2050 → WARNING (en-dessous du hard_max 2100).
    tight = AberrantValuesRule(
        LintSettings(year_max=2030, today=date(2026, 6, 10)),
        known_types=frozenset({"film"}),
    )
    reco_warn = {"id": "ubm-warn", "year": 2050, "types": ["film"]}
    issues = list(tight.check(_ctx([reco_warn])))
    assert any(
        i.severity == Severity.WARNING and i.field == "year"
        for i in issues
    )
    assert not any(
        i.severity == Severity.ERROR and i.field == "year"
        for i in issues
    )


def test_invalid_timestamp_format_flagged_error():
    rule = _rule()
    reco = {"id": "ubm-6", "timestamp": "1:2:3", "types": ["film"]}
    issues = list(rule.check(_ctx([reco])))
    err = [i for i in issues if i.field == "timestamp"]
    assert err and err[0].severity == Severity.ERROR


def test_timestamp_minutes_overflow_is_error():
    rule = _rule()
    reco = {"id": "ubm-7", "timestamp": "00:99:00", "types": ["film"]}
    issues = list(rule.check(_ctx([reco])))
    err = [i for i in issues if i.field == "timestamp"]
    assert err and err[0].severity == Severity.ERROR


def test_timestamp_mmss_is_warning_not_error_and_uses_dedicated_rule():
    """CR senior C1 : MM:SS = WARNING ``timestamp_unnormalized``, pas ERROR."""
    rule = _rule()
    reco = {"id": "ubm-mmss", "timestamp": "42:22", "types": ["film"]}
    issues = list(rule.check(_ctx([reco])))
    ts_issues = [i for i in issues if i.field == "timestamp"]
    assert ts_issues
    assert ts_issues[0].severity == Severity.WARNING
    assert ts_issues[0].rule == "timestamp_unnormalized"


def test_types_empty_flagged():
    rule = _rule()
    reco = {"id": "ubm-8", "types": []}
    issues = list(rule.check(_ctx([reco])))
    assert {i.field for i in issues} == {"types"}


def test_types_unknown_value_flagged():
    rule = _rule()
    reco = {"id": "ubm-9", "types": ["film", "wtf"]}
    issues = list(rule.check(_ctx([reco])))
    assert len(issues) == 1
    assert issues[0].field == "types"
    assert "wtf" in issues[0].message


def test_types_missing_does_not_double_report():
    rule = _rule()
    reco = {"id": "ubm-10"}
    assert list(rule.check(_ctx([reco]))) == []


def test_types_non_iterable_flagged():
    rule = _rule()
    reco = {"id": "ubm-11", "types": "film"}
    issues = list(rule.check(_ctx([reco])))
    assert {i.field for i in issues} == {"types"}


def test_rule_descriptor_attributes():
    rule = _rule()
    assert rule.name == "aberrant_values"
    assert rule.severity == Severity.ERROR
    assert isinstance(rule.description, str) and rule.description


def test_reco_with_unknown_id_uses_placeholder():
    rule = _rule()
    reco = {"year": 1500, "types": ["film"]}
    issues = list(rule.check(_ctx([reco])))
    assert issues[0].entity_id == "<unknown>"


def test_year_with_bool_value_flagged_as_non_int():
    """H1 : year=True (bool sous-type int) → ERROR explicite."""
    rule = _rule()
    reco = {"id": "ubm-x", "year": True, "types": ["film"]}
    issues = list(rule.check(_ctx([reco])))
    assert {i.field for i in issues} == {"year"}
    assert "non-int" in issues[0].message


def test_year_non_int_string_flagged_as_non_int():
    """H1 : year string → ERROR `year_type_invalid`."""
    rule = _rule()
    reco = {"id": "ubm-str", "year": "1999", "types": ["film"]}
    issues = list(rule.check(_ctx([reco])))
    assert {i.field for i in issues} == {"year"}


def test_timestamp_non_string_flagged():
    """timestamp non-str (ex. int 130) doit être flagué ERROR."""
    rule = _rule()
    reco = {"id": "ubm-z", "timestamp": 130, "types": ["film"]}
    issues = list(rule.check(_ctx([reco])))
    assert {i.field for i in issues} == {"timestamp"}


def test_known_types_lazy_uses_domain_when_no_override():
    """H2 : pas d'override → calcul lazy depuis `ItemType`."""
    rule = AberrantValuesRule(_S)  # pas de known_types override
    reco = {"id": "ubm-y", "types": ["film"]}  # "film" est dans ItemType
    assert list(rule.check(_ctx([reco]))) == []


def test_known_types_property_helper_returns_override():
    """H2 : la property `_known_types` retourne l'override quand fourni."""
    custom = frozenset({"x", "y"})
    rule = AberrantValuesRule(_S, known_types=custom)
    assert rule._known_types is custom


def test_classify_timestamp_default_branch_non_string():
    from lint.rules.aberrant_values import _classify_timestamp
    assert _classify_timestamp(None) == "invalid"
    assert _classify_timestamp([]) == "invalid"


def test_classify_timestamp_mmss_overflow_is_invalid():
    """MM:SS avec MM>=60 ou SS>=60 → invalid (pas unnormalized)."""
    from lint.rules.aberrant_values import _classify_timestamp
    assert _classify_timestamp("99:75") == "invalid"
