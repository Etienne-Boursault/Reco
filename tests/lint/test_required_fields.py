"""Tests TDD pour `RequiredFieldsRule`."""
from __future__ import annotations

from lint.rules.base import LintContext, Severity
from lint.rules.required_fields import RequiredFieldsRule


def _ctx(*, recos=(), episodes=()):
    return LintContext(source_id="ubm", recos=recos, episodes=episodes)


# ---------------------------------------------------------------------------
# Reco legacy
# ---------------------------------------------------------------------------


def test_reco_with_all_required_fields_is_clean():
    rule = RequiredFieldsRule()
    reco = {"id": "ubm-1", "episodeGuid": "g", "title": "T", "sourceId": "ubm"}
    issues = list(rule.check(_ctx(recos=(reco,))))
    assert issues == []


def test_reco_missing_id_flagged():
    rule = RequiredFieldsRule()
    reco = {"episodeGuid": "g", "title": "T", "sourceId": "ubm"}
    issues = list(rule.check(_ctx(recos=(reco,))))
    assert len(issues) == 1
    assert issues[0].field == "id"
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == "<unknown>"


def test_reco_missing_episode_guid_flagged():
    rule = RequiredFieldsRule()
    reco = {"id": "ubm-2", "title": "T", "sourceId": "ubm"}
    issues = list(rule.check(_ctx(recos=(reco,))))
    assert {i.field for i in issues} == {"episodeGuid"}
    assert issues[0].entity_id == "ubm-2"


def test_reco_missing_title_flagged():
    rule = RequiredFieldsRule()
    reco = {"id": "ubm-3", "episodeGuid": "g", "sourceId": "ubm"}
    issues = list(rule.check(_ctx(recos=(reco,))))
    assert {i.field for i in issues} == {"title"}


def test_reco_blank_title_flagged_as_missing():
    rule = RequiredFieldsRule()
    reco = {"id": "ubm-4", "episodeGuid": "g", "title": "   ", "sourceId": "ubm"}
    issues = list(rule.check(_ctx(recos=(reco,))))
    assert {i.field for i in issues} == {"title"}


def test_reco_null_field_flagged():
    rule = RequiredFieldsRule()
    reco = {"id": "ubm-5", "episodeGuid": None, "title": "T", "sourceId": "ubm"}
    issues = list(rule.check(_ctx(recos=(reco,))))
    assert {i.field for i in issues} == {"episodeGuid"}


def test_reco_missing_source_id_flagged():
    rule = RequiredFieldsRule()
    reco = {"id": "ubm-6", "episodeGuid": "g", "title": "T"}
    issues = list(rule.check(_ctx(recos=(reco,))))
    assert {i.field for i in issues} == {"sourceId"}


# ---------------------------------------------------------------------------
# Episodes legacy
# ---------------------------------------------------------------------------


def test_episode_with_all_required_fields_is_clean():
    rule = RequiredFieldsRule()
    ep = {"guid": "g", "title": "T", "sourceId": "ubm"}
    assert list(rule.check(_ctx(episodes=(ep,)))) == []


def test_episode_missing_title_flagged():
    rule = RequiredFieldsRule()
    ep = {"guid": "g", "sourceId": "ubm"}
    issues = list(rule.check(_ctx(episodes=(ep,))))
    assert len(issues) == 1
    assert issues[0].entity_type == "episode"
    assert issues[0].field == "title"
    assert issues[0].entity_id == "g"


def test_multiple_recos_each_emit_own_issue():
    rule = RequiredFieldsRule()
    recos = (
        {"id": "a", "episodeGuid": "g", "title": "T", "sourceId": "ubm"},
        {"id": "b", "episodeGuid": "g", "title": "", "sourceId": "ubm"},
    )
    issues = list(rule.check(_ctx(recos=recos)))
    assert len(issues) == 1
    assert issues[0].entity_id == "b"


def test_blank_list_value_flagged_as_missing():
    """Une liste vide est sémantiquement « absent » pour un champ requis."""
    rule = RequiredFieldsRule()
    reco = {"id": "ubm-z", "episodeGuid": [], "title": "T", "sourceId": "ubm"}
    issues = list(rule.check(_ctx(recos=(reco,))))
    assert {i.field for i in issues} == {"episodeGuid"}


def test_non_blank_non_str_value_not_flagged():
    """Une valeur non-vide non-str (int 1) n'est pas blank."""
    rule = RequiredFieldsRule()
    reco = {"id": 1, "episodeGuid": "g", "title": "T", "sourceId": "ubm"}
    # id non vide → ne déclenche pas required_fields, mais entity_id repli.
    issues = list(rule.check(_ctx(recos=(reco,))))
    assert issues == []


def test_rule_descriptor_attributes():
    rule = RequiredFieldsRule()
    assert rule.name == "required_fields"
    assert rule.severity == Severity.ERROR
    assert isinstance(rule.description, str) and rule.description
