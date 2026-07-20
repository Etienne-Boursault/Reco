"""
service.py — `LintService` orchestrateur (DIP).

Le service ne connaît que le `LintRule` Protocol et les types de base.
Il ne sait pas comment les règles sont implémentées, ne fait pas d'IO,
et ne décide pas du format du rapport (cf. `reporters/`).

H5 : ``run`` accepte tout objet duck-typé (``recos`` + ``episodes``)
plutôt qu'imposer ``isinstance(ctx, LintContext)`` — préserve LSP pour
les éventuels remplacements de contexte (tests, futurs adaptateurs).

L5 : les mappings exposés (``n_by_severity``, ``n_by_rule``) sont
``MappingProxyType`` (read-only) pour garder le rapport vraiment frozen.

#8 : ``LintReport.as_markdown()`` a été supprimé — anti-pattern d'import
retardé documenté dans ADR 0012. Tout passe désormais par les reporters
du registry (cf. ``tools.lint.reporters``).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .rules.base import LintContext, LintIssue, LintRule, Severity


@dataclass(frozen=True)
class LintReport:
    """Résultat agrégé d'un run de lint.

    Immuable. Les statistiques pré-calculées (`n_by_severity`,
    `n_by_rule`) évitent aux consommateurs de recompter.

    ``n_errors_unfiltered`` (H9) : nombre d'errors AVANT tout filtrage
    `--severity` / `--rule` côté CLI. Sert à calculer l'exit code de
    manière cohérente : le filtrage est *cosmétique* (vue), pas une
    altération de l'état du dataset.
    """

    issues: tuple[LintIssue, ...]
    n_by_severity: Mapping[Severity, int]
    n_by_rule: Mapping[str, int]
    n_errors_unfiltered: int = 0
    n_warnings_unfiltered: int = 0

    @property
    def n_total(self) -> int:
        return len(self.issues)

    @property
    def n_errors(self) -> int:
        return self.n_by_severity.get(Severity.ERROR, 0)

    @property
    def n_warnings(self) -> int:
        return self.n_by_severity.get(Severity.WARNING, 0)

    @property
    def n_infos(self) -> int:
        return self.n_by_severity.get(Severity.INFO, 0)

    def filter(
        self,
        *,
        severity: Severity | None = None,
        rule: str | None = None,
    ) -> "LintReport":
        """Renvoie un sous-rapport restreint aux issues correspondants.

        Pure (ne mute pas `self`). Recompte les agrégats sur le sous-set
        mais préserve ``n_errors_unfiltered`` (H9).
        """
        kept = tuple(
            i for i in self.issues
            if (severity is None or i.severity is severity)
            and (rule is None or i.rule == rule)
        )
        return LintReport.from_issues(
            kept,
            n_errors_unfiltered=self.n_errors_unfiltered or self.n_errors,
            n_warnings_unfiltered=self.n_warnings_unfiltered or self.n_warnings,
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    @classmethod
    def from_issues(
        cls,
        issues: Iterable[LintIssue],
        *,
        n_errors_unfiltered: int | None = None,
        n_warnings_unfiltered: int | None = None,
    ) -> "LintReport":
        issues_t = tuple(issues)
        sev_counts: Counter[Severity] = Counter()
        for i in issues_t:
            # P2 #14 : normaliser explicitement la clé en Severity
            # (au cas où une source externe pousserait un str).
            sev_counts[Severity(i.severity)] += 1
        rule_counts: Counter[str] = Counter(i.rule for i in issues_t)
        n_err = sev_counts.get(Severity.ERROR, 0)
        n_warn = sev_counts.get(Severity.WARNING, 0)
        return cls(
            issues=issues_t,
            # L5 : MappingProxyType pour read-only.
            n_by_severity=MappingProxyType(dict(sev_counts)),
            n_by_rule=MappingProxyType(dict(rule_counts)),
            n_errors_unfiltered=(
                n_errors_unfiltered if n_errors_unfiltered is not None else n_err
            ),
            n_warnings_unfiltered=(
                n_warnings_unfiltered if n_warnings_unfiltered is not None else n_warn
            ),
        )


class LintService:
    """Orchestrateur des règles (DIP).

    Substituable : injecter n'importe quelle liste de `LintRule`.
    Idempotent : `run(ctx)` peut être rappelé, ne mute pas `self`.
    """

    def __init__(self, rules: Iterable[LintRule]) -> None:
        self._rules = tuple(rules)
        for r in self._rules:
            if not isinstance(r, LintRule):
                raise TypeError(
                    f"LintService : {r!r} n'implémente pas LintRule"
                )

    @property
    def rules(self) -> tuple[LintRule, ...]:
        return self._rules

    def run(self, ctx: LintContext) -> LintReport:
        """Exécute toutes les règles sur `ctx` et agrège leurs issues.

        H5 : duck-typing — on accepte tout objet exposant ``recos`` et
        ``episodes`` (préserve LSP pour des contextes synthétiques de test
        ou de futurs adaptateurs). On vérifie aussi qu'il n'est pas une
        chaîne ou un type primitif pour éviter les fautes de frappe.
        """
        if isinstance(ctx, (str, bytes, int, float, list, tuple, dict)):
            raise TypeError(
                f"LintService.run : ctx doit ressembler à LintContext "
                f"(recos+episodes), reçu {type(ctx).__name__}"
            )
        if not (hasattr(ctx, "recos") and hasattr(ctx, "episodes")):
            raise TypeError(
                "LintService.run : ctx doit exposer .recos et .episodes"
            )
        collected: list[LintIssue] = []
        for rule in self._rules:
            collected.extend(rule.check(ctx))
        return LintReport.from_issues(collected)


__all__ = ["LintService", "LintReport"]
