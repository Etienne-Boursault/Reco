"""
tools.lint — Audit automatique du dataset (P1.5).

Couche domaine pure : détection de problèmes (champs manquants, valeurs
aberrantes, incohérences) **sans aucune dépendance IO** au cœur des règles.
La couche `service` orchestre, les `rules` décrivent, les `reporters`
formatent. La CLI vit dans `tools/lint_dataset.py`.

Principes :
  - SRP : 1 règle = 1 module = 1 préoccupation
  - OCP : ajouter une règle = nouveau fichier dans `rules/` + entrée
    dans le registry `tools.lint.rules.__init__.default_rules`
  - DIP : `LintService` consomme le `LintRule` Protocol (substitution LSP)
"""
from __future__ import annotations

from .rules.base import LintContext, LintIssue, LintRule, Severity
from .service import LintReport, LintService
from .settings import LintSettings

__all__ = [
    "LintContext",
    "LintIssue",
    "LintRule",
    "Severity",
    "LintService",
    "LintReport",
    "LintSettings",
]
