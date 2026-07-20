"""
orphan_mention.py — Détecte les ``Mention.itemId`` qui ne pointent vers
aucun ``Item`` chargé (CR senior M5).

Sévérité ERROR : une mention sans item est un trou référentiel — soit
l'item a été supprimé sans purge des mentions, soit l'itemId est faux.
"""
from __future__ import annotations

from collections.abc import Iterator

from .base import LintContext, LintIssue, LintRule, Severity


class OrphanMentionRule(LintRule):
    name = "orphan_mention"
    severity = Severity.ERROR
    description = (
        "Mention pointant vers un Item inexistant "
        "(Mention.itemId ∉ ctx.items)."
    )

    def check(self, ctx: LintContext) -> Iterator[LintIssue]:
        known_item_ids = {item.id for item in ctx.items}
        for mention in ctx.mentions:
            item_id = getattr(mention, "item_id", None)
            if not isinstance(item_id, str) or not item_id:
                continue  # validé en amont par le repo
            if item_id in known_item_ids:
                continue
            mention_id = getattr(mention, "id", None)
            entity_id = (
                mention_id if isinstance(mention_id, str) and mention_id
                else "<unknown>"
            )
            yield LintIssue(
                rule=self.name, severity=self.severity,
                entity_type="mention", entity_id=entity_id, field="itemId",
                message=(
                    f"Mention.itemId={item_id!r} ne correspond à aucun "
                    "Item chargé (orphelin)"
                ),
            )


__all__ = ["OrphanMentionRule"]
