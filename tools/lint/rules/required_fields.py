"""
required_fields.py — Détecte les champs requis manquants sur les
entités legacy (reco, episode) et les payloads mention/item dérivés.

Les `Item` et `Mention` typés sont déjà validés à la construction
(cf. domain), donc une fois chargés via les repos ils sont propres
par construction. La règle se concentre donc sur :

  - les **recos legacy** (``src/content/recos/<src>/*.json``), où le
    pipeline tolère encore des entrées partielles le temps de la
    migration P1.2 ;
  - les **épisodes legacy** qui sous-tendent le matching reco↔épisode.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .base import LintContext, LintIssue, LintRule, Severity

_RECO_REQUIRED: tuple[str, ...] = ("id", "episodeGuid", "title", "sourceId")
_EPISODE_REQUIRED: tuple[str, ...] = ("guid", "title", "sourceId")


def _is_blank(value: Any) -> bool:
    """True si ``value`` est ``None``, str vide/whitespace ou liste vide."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return True
    return False


class RequiredFieldsRule(LintRule):
    name = "required_fields"
    severity = Severity.ERROR
    description = (
        "Champ requis manquant sur une reco legacy ou un épisode legacy."
    )

    def check(self, ctx: LintContext) -> Iterator[LintIssue]:
        for reco in ctx.recos:
            yield from self._check_payload(
                payload=reco, required=_RECO_REQUIRED, entity_type="reco",
            )
        for ep in ctx.episodes:
            yield from self._check_payload(
                payload=ep, required=_EPISODE_REQUIRED, entity_type="episode",
            )

    # -- internal -------------------------------------------------------

    def _check_payload(
        self,
        *,
        payload: dict[str, Any],
        required: tuple[str, ...],
        entity_type: str,
    ) -> Iterator[LintIssue]:
        # ID lookup tolérant : on accepte que le payload soit corrompu
        # au point d'avoir un id absent (on émet alors un issue dédié
        # `<unknown>` plutôt que de crasher l'audit).
        eid_value = payload.get("id") or payload.get("guid") or "<unknown>"
        entity_id = eid_value if isinstance(eid_value, str) and eid_value.strip() else "<unknown>"
        for field_name in required:
            if _is_blank(payload.get(field_name)):
                yield LintIssue(
                    rule=self.name,
                    severity=self.severity,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field=field_name,
                    message=f"{entity_type}.{field_name} manquant ou vide",
                )


__all__ = ["RequiredFieldsRule"]
