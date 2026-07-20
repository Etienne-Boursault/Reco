"""Tests TDD pour `SuspiciousTitlesRule` (H3/H4/H8/M4/#5)."""
from __future__ import annotations

from domain.item import ExternalIds, Item, ItemType

from lint.rules.base import LintContext, Severity
from lint.rules.suspicious_titles import SuspiciousTitlesRule
from lint.settings import LintSettings


def _ctx(*, recos=(), items=(), overrides=()):
    return LintContext(
        source_id="ubm", recos=tuple(recos), items=tuple(items),
        overrides=tuple(overrides),
    )


def _item(*, id, title):
    return Item(
        id=id, types=(ItemType.FILM,), title=title,
        external_ids=ExternalIds(),
    )


def test_normal_title_is_clean():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-1", "title": "Mortel"}
    assert list(rule.check(_ctx(recos=[reco]))) == []


def test_too_short_title_flagged():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-2", "title": "Ok"}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert any("court" in i.message for i in issues)
    assert all(i.severity == Severity.WARNING for i in issues)


def test_too_long_title_flagged():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-3", "title": "A" * 150}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert any("long" in i.message for i in issues)


def test_all_caps_title_flagged():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-4", "title": "BREAKING BAD"}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert any("majuscules" in i.message for i in issues)


def test_brackets_in_title_flagged():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-5", "title": "Mortel [VF]"}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert any("[" in i.message or "extraction" in i.message for i in issues)


def test_known_format_suffix_flagged():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-6", "title": "Mortel (saison 2)"}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert any("format" in i.message for i in issues)


def test_empty_title_silent_belongs_to_required_fields():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-7", "title": "   "}
    assert list(rule.check(_ctx(recos=[reco]))) == []


def test_non_str_title_silent():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-8", "title": None}
    assert list(rule.check(_ctx(recos=[reco]))) == []


def test_short_acronym_uppercase_not_flagged_as_caps():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-9", "title": "NASA"}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert not any("majuscules" in i.message for i in issues)


def test_vost_suffix_flagged():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-10", "title": "Film X (VOST)"}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert any("format" in i.message for i in issues)


def test_rule_descriptor():
    rule = SuspiciousTitlesRule()
    assert rule.name == "suspicious_titles"
    assert rule.severity == Severity.WARNING


def test_reco_without_id_uses_placeholder():
    rule = SuspiciousTitlesRule()
    reco = {"title": "AB"}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert issues[0].entity_id == "<unknown>"


# ---------------------------------------------------------------------------
# H3 — paramétrabilité
# ---------------------------------------------------------------------------


def test_min_len_parameter_overrides_settings():
    rule = SuspiciousTitlesRule(min_len=5)
    reco = {"id": "x", "title": "ABCD"}  # 4 chars → court
    issues = list(rule.check(_ctx(recos=[reco])))
    assert any("court" in i.message for i in issues)


def test_caps_threshold_parameter_overrides_settings():
    rule = SuspiciousTitlesRule(all_caps_threshold=10)
    reco = {"id": "x", "title": "BREAKING"}  # 8 chars, sous le seuil 10
    issues = list(rule.check(_ctx(recos=[reco])))
    assert not any("majuscules" in i.message for i in issues)


def test_extra_patterns_param_extends_default_set():
    rule = SuspiciousTitlesRule(extra_patterns=(r"\(custom\)",))
    reco = {"id": "x", "title": "Truc (custom)"}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert any("format" in i.message for i in issues)


def test_source_specific_patterns_via_settings():
    """#5 : patterns injectés depuis settings (source-aware)."""
    s = LintSettings(title_suspicious_patterns=(r"\(spéciale\)",))
    rule = SuspiciousTitlesRule(s)
    reco = {"id": "x", "title": "Émission (spéciale)"}
    issues = list(rule.check(_ctx(recos=[reco])))
    assert any("format" in i.message for i in issues)


# ---------------------------------------------------------------------------
# M4 — couverture des Items
# ---------------------------------------------------------------------------


def test_rule_also_covers_items_not_just_recos():
    rule = SuspiciousTitlesRule()
    item = _item(id="aaa11111", title="Mortel [VF]")
    issues = list(rule.check(_ctx(items=[item])))
    assert any(i.entity_type == "item" for i in issues)


# ---------------------------------------------------------------------------
# H4 — overrides
# ---------------------------------------------------------------------------


def test_override_silences_title_warning():
    rule = SuspiciousTitlesRule()
    reco = {"id": "ubm-ov", "title": "AB"}
    overrides = [{"entity_id": "ubm-ov", "field": "title", "ignore": True}]
    assert list(rule.check(_ctx(recos=[reco], overrides=overrides))) == []


def test_only_first_matching_pattern_emits_one_issue():
    """Un seul issue 'format' par titre même si plusieurs patterns matchent."""
    rule = SuspiciousTitlesRule(
        extra_patterns=(r"\(saison\s+\d+\)", r"\(episode\s+\d+\)"),
    )
    reco = {"id": "x", "title": "Truc (saison 2) (episode 1)"}
    issues = list(rule.check(_ctx(recos=[reco])))
    fmt = [i for i in issues if "format" in i.message]
    assert len(fmt) == 1


def test_override_silences_item_title_warning():
    rule = SuspiciousTitlesRule()
    item = _item(id="aaa11111", title="A" * 200)
    overrides = [{"entity_id": "aaa11111", "field": "title", "ignore": True}]
    assert list(rule.check(_ctx(items=[item], overrides=overrides))) == []
