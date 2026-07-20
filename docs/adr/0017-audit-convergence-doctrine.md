# ADR 0017 — Doctrine convergence audit (méta)

- Statut : Acceptée — **Superseded by ADR 0019** (`audit_core/` unifié)
- Date : 2026-06-10
- Décideurs : équipe Reco
- ADRs liés : 0012 (linter), 0013 (match audit), 0014 (enrich audit),
  0015 (sidecar match), 0016 (méta-pipeline audit)

## Contexte

Trois sous-systèmes d'audit cohabitent désormais — `tools/lint/`,
`tools/match_audit/`, `tools/enrich_audit/` — chacun produit par un
sprint distinct, chacun avec ses propres types `Severity`,
`Settings`, `Reporter`, conventions de stockage et `cli_runner`.

Trois divergences à arbitrer :

1. **Stockage** : in-place (drapeau sur l'épisode/item),
   sidecar JSON per-entity, rapport agrégé Markdown/JSON.
2. **Temporalité** : one-shot (run jetable) vs historisée (run daté
   conservé en `audit/`).
3. **Consommateur** : humain (Markdown), CI (exit code), UI (sidecar
   per-entity exploitable par le review_server).

L'option « extraire un `tools/audit_core/` partagé maintenant » a été
*explicitement écartée* pour cette PR (zones interdites des autres
fixers — risque de collisions imprévisibles, dette d'intégration plus
grosse que le bénéfice). On reporte à une **CR cumulative fin Phase 1**.

## Décision

### Tableau des 3 axes

| Axe          | linter (P1.5)           | match_audit (P1.6)     | enrich_audit (P1.7)      |
|--------------|-------------------------|------------------------|--------------------------|
| Stockage     | rapport agrégé MD/JSON  | drapeau in-place + sidecar | sidecar per-item     |
| Temporalité  | historisée (`audit/<date>__lint__<src>.md`) | one-shot (drapeau) | one-shot (sidecar)       |
| Consommateur | humain + CI (exit code) | review_server UI       | review_server UI         |

### Doctrine

- **Linter** = rapport agrégé sur le dataset entier d'une source.
  Produit Markdown (humain) et JSON (CI, futur dashboard). Historisé
  par date pour suivi temporel.
- **Match audit** = drapeau sur l'épisode (in-place) + sidecar JSON
  par épisode quand une heuristique fine doit être inspectée par l'UI.
  One-shot : la prochaine run écrase le drapeau.
- **Enrich audit** = sidecar par Item, exploitable par l'UI pour les
  pastilles « TMDB suspect ».

### Convergence reportée

`tools/audit_core/` (Severity unifié, Reporter Protocol partagé,
RunOptions générique) reportée à **Sprint 2 fin Phase 1**, sur une PR
dédiée *après* que les trois sous-systèmes auront stabilisé leurs
conventions (= 2-3 itérations en prod). Bénéfice : on évite un BDUF
(big design up front) basé sur les conventions provisoires.

### Divergences mineures assumées

État réel (vérifié 2026-06-10, à corriger par ADR 0019) :

- `lint.rules.base.Severity` (StrEnum) : `ERROR/WARNING/INFO`.
- `match_audit.types.Severity` (str+Enum) : `ERROR/WARNING` uniquement.
- `enrich_audit.types.Severity` (StrEnum) : `INFO/WARNING/CRITICAL`.

Aucun module n'utilise les niveaux `block` ou `warn` initialement décrits :
la doctrine `0017` documentait une cible, pas l'implémenté. ADR 0019
ré-aligne les conventions sur 4 niveaux unifiés `{INFO, WARNING, ERROR,
CRITICAL}` avec mapping rétro-compat préservé.

Renommage côté linter à `error→fail`/`warning→warn` *envisagé* en
Sprint 2 dans le cadre de la convergence ; non-bloquant pour P1.5.

## Conséquences

**Positives** :
- Aucun blocage cross-fixers : chaque sous-système avance
  indépendamment.
- Les trois sous-systèmes accumulent du feedback réel avant la
  fusion → meilleure abstraction.

**Négatives** :
- Dette technique cumulée : 3× `Severity`, 3× `Reporter`, 3×
  `cli_runner` boilerplate. Documentée et budgétée.
- Forks Reco devront naviguer 3 conventions différentes pour
  ajouter un audit custom — partiellement compensé par les patterns
  similaires (settings injectables, cli_runner, registry).

## Plan de migration Sprint 2

1. Geler les conventions (`Severity`, `Reporter Protocol`,
   `cli_runner` shape) des trois sous-systèmes.
2. Identifier les invariants communs (tous trois exposent `name`,
   `severity`, `description`, `check(ctx) -> issues`).
3. Extraire `tools/audit_core/` :
   - `Severity` unifié (mapping de retro-compat).
   - `Reporter` Protocol commun + registry.
   - `cli_runner.RunOptions[Ctx, Report]` générique.
4. Migrer les 3 sous-systèmes en 3 PRs successives, tests de
   non-régression à chaque étape.
5. Supprimer la duplication.

## Notes

- Cette PR (linter) prépare la convergence en suivant strictement le
  pattern `match_audit/settings.py:from_source_extra()` — toute future
  unification du settings shape sera triviale.
- Le `MetaLintReport` signature (cf. ADR 0012 update) est forward-compat
  avec un agrégateur cross-sous-systèmes.
