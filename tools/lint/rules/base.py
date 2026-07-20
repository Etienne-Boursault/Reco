"""
base.py — Types fondamentaux du linter (zéro IO).

`Severity` / `LintIssue` / `LintContext` / `LintRule` forment le contrat
stable que les règles concrètes et `LintService` consomment. Tout le reste
(implémentations de règles, reporters, service, CLI) dépend de ce module
et de rien d'autre du package.

Notes :
  - ``LintRule`` est ``@runtime_checkable`` : ``isinstance(r, LintRule)``
    coûte un *structural check* (lent à l'échelle de millions d'appels).
    Acceptable pour 5-10 règles, à monitorer si on dépasse 100. (CR archi #17)
  - Le hook « auto-fix » (CR senior L6) n'est pas implémenté ; il viendra
    via un Protocol distinct ``AutoFixableRule(LintRule)`` qui ajoutera
    une méthode ``fix(ctx) -> tuple[LintIssue, dict[str, Any]]``. Préparé
    en P2 (cf. ADR 0012).
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from audit_core.types import Severity  # SSOT — cf. ADR 0019

if TYPE_CHECKING:  # pragma: no cover
    from tools.config.schema import SourceConfig
    from tools.domain.item import Item
    from tools.domain.mention import Mention

# Note ADR 0019 : ``Severity`` est réexporté depuis ``audit_core``. Le linter
# n'utilise que ``ERROR``/``WARNING``/``INFO`` mais ``CRITICAL`` reste
# accessible pour les modules consommateurs (option B — 4 niveaux unifiés,
# zéro casse de sérialisation).


@dataclass(frozen=True)
class LintIssue:
    """Problème détecté par une règle.

    Immuable : un issue est un constat ; toute « correction » produit un
    autre issue (auto-fix hors scope P1.5, cf. ADR 0012).
    """

    rule: str
    severity: Severity
    entity_type: str
    """``"reco"`` | ``"item"`` | ``"mention"`` | ``"episode"`` |
    ``"cluster"`` | ``"dataset"`` — convention libre, gardée str pour ne
    pas figer l'enum (extension forward-compat)."""
    entity_id: str
    field: str | None
    message: str
    cluster_id: str | None = None
    """ID stable d'un *cluster* d'entités lié par l'issue (ex. cluster
    de doublons). Permet à un seul issue de représenter N entités sans
    exploser le rapport (CR senior C2)."""

    def __post_init__(self) -> None:
        if not isinstance(self.rule, str) or not self.rule.strip():
            raise ValueError("LintIssue.rule ne peut pas être vide")
        if not isinstance(self.severity, Severity):
            raise ValueError(
                f"LintIssue.severity doit être Severity, "
                f"reçu {type(self.severity).__name__}"
            )
        if not isinstance(self.entity_type, str) or not self.entity_type.strip():
            raise ValueError("LintIssue.entity_type ne peut pas être vide")
        if not isinstance(self.entity_id, str) or not self.entity_id.strip():
            raise ValueError("LintIssue.entity_id ne peut pas être vide")
        if self.field is not None and (
            not isinstance(self.field, str) or not self.field.strip()
        ):
            raise ValueError("LintIssue.field doit être None ou str non vide")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("LintIssue.message ne peut pas être vide")
        if self.cluster_id is not None and (
            not isinstance(self.cluster_id, str) or not self.cluster_id.strip()
        ):
            raise ValueError("LintIssue.cluster_id doit être None ou str non vide")


@dataclass(frozen=True)
class LintContext:
    """Données chargées du dataset que les règles consultent.

    Tout ce qui est lourd (lecture disque) est fait UNE FOIS par le
    composer puis injecté. Les règles travaillent sur ces données en
    lecture seule.

    Les listes sont gardées en `tuple` pour préserver l'invariant
    « contexte immuable » que la signature dataclass(frozen=True)
    n'impose pas sur les éléments mutables.

    L'index ``_episode_index`` est construit une seule fois (H6) puis
    exposé via ``MappingProxyType`` (read-only).
    """

    source_id: str
    recos: tuple[dict[str, Any], ...] = ()
    items: tuple["Item", ...] = ()
    mentions: tuple["Mention", ...] = ()
    episodes: tuple[dict[str, Any], ...] = ()
    source_config: "SourceConfig | None" = None
    overrides: tuple[dict[str, Any], ...] = ()
    """Overrides chargés depuis le dataset (CR senior H4) — la règle
    ``recommendedby_consistency`` ou ``suspicious_titles`` les consulte
    avant de flag. Forme générique (dict) pour ne pas coupler à un
    schéma ; clés conventionnelles : ``entity_id``, ``field``, ``ignore``."""
    _episode_index: Mapping[str, dict[str, Any]] = field(
        default=MappingProxyType({}), init=False, repr=False, compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("LintContext.source_id ne peut pas être vide")
        for name in ("recos", "items", "mentions", "episodes", "overrides"):
            v = getattr(self, name)
            if not isinstance(v, tuple):
                raise ValueError(
                    f"LintContext.{name} doit être un tuple, reçu {type(v).__name__}"
                )
        # H6 : construire le dict d'index *puis* le verrouiller en
        # MappingProxyType — frozen=True n'empêche pas la mutation in-place
        # du dict, on enlève donc tout pied tendu en exposant un proxy.
        idx: dict[str, dict[str, Any]] = {}
        for ep in self.episodes:
            guid = ep.get("guid")
            if isinstance(guid, str) and guid:
                idx[guid] = ep
        object.__setattr__(self, "_episode_index", MappingProxyType(idx))

    def episode_by_guid(self, guid: str | None) -> dict[str, Any] | None:
        """Retourne l'épisode dont `guid == guid`, ou None."""
        if not isinstance(guid, str) or not guid:
            return None
        return self._episode_index.get(guid)

    def is_overridden(self, *, entity_id: str, field: str | None) -> bool:
        """True si un override a explicitement marqué ``(entity_id, field)``
        à ignorer. Sert aux règles WARNING qui veulent respecter une
        décision humaine (CR senior H4).
        """
        for o in self.overrides:
            if o.get("entity_id") != entity_id:
                continue
            if field is not None and o.get("field") not in (None, field):
                continue
            if o.get("ignore"):
                return True
        return False


@runtime_checkable
class LintRule(Protocol):
    """Contrat d'une règle de lint.

    Une règle est un *callable d'analyse* : reçoit le contexte complet
    et émet 0..N issues. Elle ne mute rien, ne fait pas d'IO.

    Note de perf (CR archi #17) : ``@runtime_checkable`` rend
    ``isinstance(r, LintRule)`` plus lent (vérification structurale par
    introspection). On l'utilise au constructeur du service uniquement,
    pas dans une boucle chaude.
    """

    name: str
    severity: Severity
    description: str

    def check(self, ctx: LintContext) -> Iterator[LintIssue]:
        """Analyse le contexte et émet les issues détectés."""
        ...  # pragma: no cover


# Note (CR senior L6) : hook auto-fix prévu en P2 — une règle pourra
# implémenter `AutoFixableRule(LintRule)` en ajoutant une méthode
# `fix(ctx, issue) -> dict[str, Any]` qui retourne le patch à appliquer.
# Pas d'impl dans P1.5 (linter strictement lecture seule, cf. ADR 0012).


__all__ = [
    "Severity",
    "LintIssue",
    "LintContext",
    "LintRule",
]
