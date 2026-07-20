"""Tests TDD pour `OrphanMentionRule` (CR senior M5)."""
from __future__ import annotations

from domain.item import ExternalIds, Item, ItemType
from domain.mention import Mention, SourceRef

from lint.rules.base import LintContext, Severity
from lint.rules.orphan_mention import OrphanMentionRule


def _item(item_id: str) -> Item:
    return Item(
        id=item_id, types=(ItemType.FILM,), title="T",
        external_ids=ExternalIds(),
    )


def _mention(*, mention_id: str, item_id: str) -> Mention:
    return Mention(
        id=mention_id, item_id=item_id,
        source_ref=SourceRef(source_id="ubm", episode_guid="g"),
    )


def test_mention_pointing_to_known_item_is_clean():
    rule = OrphanMentionRule()
    item = _item("aaa11111")
    mention = _mention(mention_id="mmm11111", item_id="aaa11111")
    ctx = LintContext(source_id="ubm", items=(item,), mentions=(mention,))
    assert list(rule.check(ctx)) == []


def test_mention_pointing_to_unknown_item_flagged_error():
    rule = OrphanMentionRule()
    item = _item("aaa11111")
    mention = _mention(mention_id="mmm22222", item_id="zzzghost9")
    ctx = LintContext(source_id="ubm", items=(item,), mentions=(mention,))
    issues = list(rule.check(ctx))
    assert len(issues) == 1
    assert issues[0].rule == "orphan_mention"
    assert issues[0].severity == Severity.ERROR
    assert issues[0].entity_id == "mmm22222"
    assert "zzzghost9" in issues[0].message


def test_no_mentions_is_clean():
    rule = OrphanMentionRule()
    ctx = LintContext(source_id="ubm", items=(_item("aaa11111"),))
    assert list(rule.check(ctx)) == []


def test_mention_without_item_id_attr_is_silent():
    """Garde-fou : mention sans attribut `item_id` exploitable → skip."""
    rule = OrphanMentionRule()

    class _M:
        id = "mmm"
        item_id = ""  # invalide → skipped silencieusement

    ctx = LintContext(source_id="ubm", items=(), mentions=())
    # type: ignore — on simule via override de ctx.mentions
    object.__setattr__(ctx, "mentions", (_M(),))
    assert list(rule.check(ctx)) == []


def test_rule_descriptor():
    rule = OrphanMentionRule()
    assert rule.name == "orphan_mention"
    assert rule.severity == Severity.ERROR
    assert isinstance(rule.description, str) and rule.description
