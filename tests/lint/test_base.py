"""Tests des types de base du linter (Severity, LintIssue, LintContext)."""
from __future__ import annotations

import pytest

from lint.rules.base import LintContext, LintIssue, LintRule, Severity


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


def test_severity_values_are_stable_strings():
    assert Severity.ERROR == "error"
    assert Severity.WARNING == "warning"
    assert Severity.INFO == "info"


# ---------------------------------------------------------------------------
# LintIssue
# ---------------------------------------------------------------------------


def test_lint_issue_minimal_valid():
    issue = LintIssue(
        rule="required_fields", severity=Severity.ERROR,
        entity_type="reco", entity_id="ubm-0001", field="title",
        message="title manquant",
    )
    assert issue.rule == "required_fields"
    assert issue.field == "title"
    assert issue.cluster_id is None


def test_lint_issue_with_cluster_id():
    """C2 : cluster_id permet de regrouper N entités dans un seul issue."""
    issue = LintIssue(
        rule="duplicate_canonical", severity=Severity.ERROR,
        entity_type="cluster", entity_id="abcdef123456",
        field="canonical_key", message="3 doublons",
        cluster_id="abcdef123456",
    )
    assert issue.cluster_id == "abcdef123456"


def test_lint_issue_field_can_be_none():
    issue = LintIssue(
        rule="r", severity=Severity.INFO, entity_type="item",
        entity_id="abc12345", field=None, message="ok",
    )
    assert issue.field is None


def test_lint_issue_is_frozen():
    issue = LintIssue(
        rule="r", severity=Severity.INFO, entity_type="reco",
        entity_id="x", field=None, message="m",
    )
    with pytest.raises(Exception):
        issue.message = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rule": ""}, {"rule": "   "},
        {"entity_type": ""}, {"entity_id": ""}, {"message": ""},
        {"field": ""}, {"field": "  "},
        {"cluster_id": ""}, {"cluster_id": "   "},
    ],
)
def test_lint_issue_rejects_empty_fields(kwargs):
    base = dict(
        rule="r", severity=Severity.ERROR, entity_type="reco",
        entity_id="x", field="t", message="m",
    )
    base.update(kwargs)
    with pytest.raises(ValueError):
        LintIssue(**base)


def test_lint_issue_rejects_non_severity():
    with pytest.raises(ValueError):
        LintIssue(
            rule="r", severity="error",  # type: ignore[arg-type]
            entity_type="reco", entity_id="x", field=None, message="m",
        )


# ---------------------------------------------------------------------------
# LintContext
# ---------------------------------------------------------------------------


def test_lint_context_minimal():
    ctx = LintContext(source_id="ubm")
    assert ctx.source_id == "ubm"
    assert ctx.recos == ()
    assert ctx.episodes == ()
    assert ctx.overrides == ()


def test_lint_context_rejects_blank_source_id():
    with pytest.raises(ValueError):
        LintContext(source_id="")


def test_lint_context_rejects_list_collections():
    with pytest.raises(ValueError):
        LintContext(source_id="ubm", recos=[])  # type: ignore[arg-type]


def test_lint_context_rejects_list_overrides():
    with pytest.raises(ValueError):
        LintContext(source_id="ubm", overrides=[])  # type: ignore[arg-type]


def test_episode_by_guid_returns_match():
    ep = {"guid": "abc-123", "title": "Test"}
    ctx = LintContext(source_id="ubm", episodes=(ep,))
    assert ctx.episode_by_guid("abc-123") is ep


def test_episode_by_guid_returns_none_when_missing():
    ctx = LintContext(source_id="ubm")
    assert ctx.episode_by_guid("nope") is None
    assert ctx.episode_by_guid(None) is None
    assert ctx.episode_by_guid("") is None


def test_episode_index_skips_episodes_without_guid():
    eps = ({"title": "no guid"}, {"guid": "", "title": "blank"})
    ctx = LintContext(source_id="ubm", episodes=eps)
    assert ctx.episode_by_guid("") is None


def test_episode_index_is_read_only_mapping_proxy():
    """H6 : l'index ne doit pas être muté de l'extérieur."""
    ep = {"guid": "g1", "title": "T"}
    ctx = LintContext(source_id="ubm", episodes=(ep,))
    # `_episode_index` est un MappingProxyType → support __setitem__ refusé.
    with pytest.raises(TypeError):
        ctx._episode_index["nope"] = {}  # type: ignore[index]


def test_is_overridden_default_false():
    ctx = LintContext(source_id="ubm")
    assert ctx.is_overridden(entity_id="x", field="title") is False


def test_is_overridden_true_when_match_with_field():
    ctx = LintContext(
        source_id="ubm",
        overrides=({"entity_id": "x", "field": "title", "ignore": True},),
    )
    assert ctx.is_overridden(entity_id="x", field="title") is True


def test_is_overridden_field_wildcard():
    """Un override sans `field` matche n'importe quel champ pour l'entité."""
    ctx = LintContext(
        source_id="ubm",
        overrides=({"entity_id": "x", "ignore": True},),
    )
    assert ctx.is_overridden(entity_id="x", field="title") is True
    assert ctx.is_overridden(entity_id="x", field="year") is True


def test_is_overridden_other_entity_false():
    ctx = LintContext(
        source_id="ubm",
        overrides=({"entity_id": "x", "ignore": True},),
    )
    assert ctx.is_overridden(entity_id="y", field="title") is False


def test_is_overridden_field_mismatch_skips_override():
    """Couvre la branche `field != requested_field`."""
    ctx = LintContext(
        source_id="ubm",
        overrides=({"entity_id": "x", "field": "year", "ignore": True},),
    )
    assert ctx.is_overridden(entity_id="x", field="title") is False


def test_is_overridden_ignore_false_means_no_skip():
    ctx = LintContext(
        source_id="ubm",
        overrides=({"entity_id": "x", "ignore": False},),
    )
    assert ctx.is_overridden(entity_id="x", field="title") is False


# ---------------------------------------------------------------------------
# LintRule Protocol
# ---------------------------------------------------------------------------


def test_runtime_check_lintrule_protocol():
    """L9 : `@runtime_checkable` vérifie la PRÉSENCE des noms, pas les
    signatures. Limitation documentée.
    """
    class _Dummy:
        name = "dummy"
        severity = Severity.INFO
        description = "noop"

        def check(self, ctx):
            return iter(())

    assert isinstance(_Dummy(), LintRule)


def test_runtime_check_rejects_incomplete_rule():
    class _NotARule:
        name = "x"

    assert not isinstance(_NotARule(), LintRule)
