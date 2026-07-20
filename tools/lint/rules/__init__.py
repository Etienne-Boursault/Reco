"""
rules/__init__.py — Registry des règles de lint (OCP).

Pour ajouter une règle :
  1. Créer ``rules/<my_rule>.py`` avec une classe implémentant ``LintRule``
     (cf. ``base.LintRule``).
  2. L'importer ici et l'ajouter à ``default_rules()``.

CR archi #2 : chaque règle reçoit un ``LintSettings`` injecté à la
construction (seuils, patterns suspects, today). Les règles qui n'en
ont pas besoin ignorent simplement l'argument.

Le filtrage ``enabled_rules`` / ``disabled_rules`` est appliqué ici (pas
côté service) pour que ce soit une décision de *composition* visible
dans le composer racine.
"""
from __future__ import annotations

from .aberrant_values import AberrantValuesRule
from .base import LintContext, LintIssue, LintRule, Severity
from .duplicate_canonical import (
    DuplicateCanonicalKeyRule,
    DuplicateCanonicalRule,
    DuplicateExternalIdRule,
)
from .orphan_mention import OrphanMentionRule
from .recommendedby_consistency import RecommendedByConsistencyRule
from .required_fields import RequiredFieldsRule
from .suspicious_titles import SuspiciousTitlesRule
from ..settings import LintSettings


def default_rules(settings: LintSettings | None = None) -> tuple[LintRule, ...]:
    """Renvoie une instance fraîche de chaque règle livrée par défaut.

    Factory plutôt que constante figée pour autoriser un service de
    composer son propre subset sans mutation globale.

    ``settings`` injecté dans les règles qui en consomment (P0 #2). Les
    règles non-paramétrables (`RequiredFieldsRule`, `OrphanMentionRule`,
    `DuplicateExternalIdRule`) ignorent simplement l'argument.
    """
    s = settings or LintSettings()
    all_rules: tuple[LintRule, ...] = (
        RequiredFieldsRule(),
        AberrantValuesRule(s),
        RecommendedByConsistencyRule(),
        SuspiciousTitlesRule(s),
        DuplicateCanonicalKeyRule(),
        DuplicateExternalIdRule(id_kind="tmdb"),
        OrphanMentionRule(),
    )
    return tuple(r for r in all_rules if s.is_rule_enabled(r.name))


__all__ = [
    "LintContext",
    "LintIssue",
    "LintRule",
    "Severity",
    "LintSettings",
    "RequiredFieldsRule",
    "AberrantValuesRule",
    "RecommendedByConsistencyRule",
    "SuspiciousTitlesRule",
    "DuplicateCanonicalRule",
    "DuplicateCanonicalKeyRule",
    "DuplicateExternalIdRule",
    "OrphanMentionRule",
    "default_rules",
]
