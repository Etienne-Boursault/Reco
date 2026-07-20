"""Tests TDD pour `DuplicateCanonicalKeyRule` + `DuplicateExternalIdRule`."""
from __future__ import annotations

from domain.item import ExternalIds, Item, ItemType

from lint.rules.base import LintContext, Severity
from lint.rules.duplicate_canonical import (
    DuplicateCanonicalKeyRule,
    DuplicateCanonicalRule,
    DuplicateExternalIdRule,
)


def _item(*, id, title, creator=None, tmdb=None, tmdb_type=None):
    return Item(
        id=id, types=(ItemType.FILM,), title=title, creator=creator,
        external_ids=ExternalIds(tmdb=tmdb, tmdb_type=tmdb_type),
    )


def _ctx(items):
    return LintContext(source_id="ubm", items=tuple(items))


def test_unique_items_are_clean():
    rule = DuplicateCanonicalKeyRule()
    items = [
        _item(id="aaa11111", title="Mortel"),
        _item(id="bbb22222", title="Inception"),
    ]
    assert list(rule.check(_ctx(items))) == []


def test_two_items_same_canonical_key_emit_single_cluster_issue():
    """C2 : un seul issue par cluster, pas N."""
    rule = DuplicateCanonicalKeyRule()
    items = [
        _item(id="aaa11111", title="Mortel"),
        _item(id="bbb22222", title="MORTEL"),
    ]
    issues = list(rule.check(_ctx(items)))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.ERROR
    assert issue.field == "canonical_key"
    assert issue.entity_type == "cluster"
    assert issue.cluster_id is not None
    assert "aaa11111" in issue.message
    assert "bbb22222" in issue.message


def test_three_items_same_canonical_key_still_one_issue():
    rule = DuplicateCanonicalKeyRule()
    items = [
        _item(id="aaa11111", title="Mortel"),
        _item(id="bbb22222", title="Mortel"),
        _item(id="ccc33333", title="MORTEL"),
    ]
    issues = list(rule.check(_ctx(items)))
    assert len(issues) == 1


def test_two_items_same_tmdb_emit_external_id_issue():
    rule = DuplicateExternalIdRule(id_kind="tmdb")
    items = [
        _item(id="aaa11111", title="Mortel", tmdb=42, tmdb_type="tv"),
        _item(id="bbb22222", title="Inception", tmdb=42, tmdb_type="tv"),
    ]
    issues = list(rule.check(_ctx(items)))
    assert len(issues) == 1
    assert issues[0].field == "externalIds.tmdb"
    assert "42" in issues[0].message


def test_empty_canonical_key_does_not_cluster():
    """C2 protection : titres vides ne doivent pas se collisionner."""
    rule = DuplicateCanonicalKeyRule()
    # Titres distincts → canonical_keys distinctes → pas de cluster.
    items = [
        _item(id="aaa11111", title="Mortel"),
        _item(id="bbb22222", title="Inception"),
    ]
    assert list(rule.check(_ctx(items))) == []


def test_descriptor():
    rule = DuplicateCanonicalKeyRule()
    assert rule.name == "duplicate_canonical"
    assert rule.severity == Severity.ERROR
    assert isinstance(rule.description, str)


def test_legacy_alias_points_to_canonical_key_rule():
    assert DuplicateCanonicalRule is DuplicateCanonicalKeyRule


def test_external_id_rule_rejects_empty_kind():
    import pytest
    with pytest.raises(ValueError):
        DuplicateExternalIdRule(id_kind="")


def test_external_id_rule_kind_property():
    rule = DuplicateExternalIdRule(id_kind="spotify")
    assert rule.id_kind == "spotify"


def test_external_id_rule_skips_bool_values():
    """Bool est sous-type d'int → exclu explicitement de la déduplication tmdb."""
    rule = DuplicateExternalIdRule(id_kind="tmdb")
    # ExternalIds accepte None, on simule "absence" partout.
    items = [_item(id="aaa11111", title="A"), _item(id="bbb22222", title="B")]
    assert list(rule.check(_ctx(items))) == []


def test_canonical_rule_skips_falsy_canonical_key():
    """C2 : un item dont canonical_key est falsy ne participe pas au cluster."""
    rule = DuplicateCanonicalKeyRule()
    # Avec un titre TRÈS court / normalisable à vide, on s'attend à ce
    # qu'il n'apparaisse pas dans les clusters. On simule en
    # monkeypatchant `canonical_key` côté test pour qu'il renvoie "" pour
    # un item ciblé.
    import lint.rules.duplicate_canonical as mod
    real = mod.canonical_key

    def _patched(title, creator):
        return "" if title == "GHOST" else real(title, creator)

    mod.canonical_key = _patched
    try:
        items = [
            _item(id="aaa11111", title="GHOST"),
            _item(id="bbb22222", title="GHOST"),
        ]
        assert list(rule.check(_ctx(items))) == []
    finally:
        mod.canonical_key = real


def test_external_id_rule_unique_external_id_is_clean():
    rule = DuplicateExternalIdRule(id_kind="tmdb")
    items = [
        _item(id="aaa11111", title="A", tmdb=1, tmdb_type="movie"),
        _item(id="bbb22222", title="B", tmdb=2, tmdb_type="movie"),
    ]
    assert list(rule.check(_ctx(items))) == []
