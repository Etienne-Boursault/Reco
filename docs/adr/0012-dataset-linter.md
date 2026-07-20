# ADR 0012 — Linter du dataset (audit automatique)

- Statut : Acceptée (mise à jour 2026-06-10 — révision CR senior + archi)
- Date : 2026-06-10
- Décideurs : équipe Reco
- ADRs liés : 0017 (convergence audit), 0018 (nommage rapports)

## Contexte

Phase 1 item #5 de la roadmap. Le dataset compte ~2 866 recos legacy,
2 651 Items et 2 866 Mentions. Au fil des migrations (P1.2 reco→Item/
Mention, P1.4 multi-types), des incohérences se sont accumulées sans
mécanisme systématique pour les détecter :

- timestamps mal extraits (ex. `42:22` au lieu de `00:42:22`),
- `recommendedBy` ne matchant aucun host/guest de l'épisode,
- Items distincts pointant le même `tmdb_id` (= bug merge),
- titres bruts contenant des artefacts d'extraction LLM (`[VOST]`,
  `(saison 2)`),
- années aberrantes (ex. année `30` → year < 1800),
- Mentions orphelines (itemId pointant un Item supprimé).

Trois pistes considérées :

1. **Étendre les schémas Zod côté Astro.** Rejeté : Zod valide la forme
   d'un fichier isolé ; pas d'invariants cross-entités.
2. **Greper / script ad hoc.** Rejeté : pas testable, pas extensible.
3. **Linter dédié, en couche domaine pure, exécuté par CLI.** Retenu :
   séparation claire, TDD-friendly, extensible par OCP.

## Décision

On introduit `tools/lint/` (couche domaine pure) et `tools/lint_dataset.py`
(CLI) :

```
tools/lint/
  rules/
    base.py                         # Severity, LintIssue, LintContext, LintRule (Protocol)
    required_fields.py
    aberrant_values.py
    recommendedby_consistency.py
    suspicious_titles.py
    duplicate_canonical.py          # DuplicateCanonicalKey + DuplicateExternalId
    orphan_mention.py
  reporters/
    summary.py
    markdown_reporter.py
    json_reporter.py
    __init__.py                     # registry REPORTERS (P1 #7)
  service.py                        # LintService, LintReport
  settings.py                       # LintSettings (P0 #2)
  loaders.py                        # DatasetLoader Protocol + JsonDatasetLoader
  cli_runner.py                     # LintRunOptions / run_lint (P1 #9)
tools/lint_dataset.py               # CLI fine couche argparse
```

### Sévérité

- `ERROR` — incohérence factuelle à corriger. Bloque la CI.
- `WARNING` — heuristique. À inspecter mais ne bloque pas.
- `INFO` — observations (`orphan_episode_ref` par exemple).

> Note de divergence cross-modules : `match_audit` utilise
> `block/warn/info`, `enrich_audit` un score 0-1. Cf. ADR 0017 pour la
> doctrine de convergence reportée Sprint 2.

### Exit code

- `0` — aucun issue.
- `1` — au moins un `ERROR` (compteur **unfiltered** — le filtrage CLI
  est cosmétique, CR senior H9).
- `2` — uniquement des `WARNING`.
- `4` — verrou pipeline busy.

### Extension OCP — ajouter une règle

1. créer `tools/lint/rules/<my_rule>.py` (classe `LintRule`-conforme,
   acceptant `LintSettings` au constructeur si paramétrable).
2. l'ajouter à `tools/lint/rules/__init__.default_rules()`.

### Settings injectables (P0 #2)

Chaque règle paramétrable reçoit un `LintSettings`. Pattern copié de
`tools/match_audit/settings.py` :

- `year_min` / `year_max` / `title_*` / `today` injectés.
- `title_suspicious_patterns` injectables = patterns **source-aware**
  (le linter ne hardcode plus le FR « un-bon-moment » — P0 #5).
- `enabled_rules` / `disabled_rules` pour qu'un fork choisisse son
  subset sans patcher le code.
- `LintSettings.from_source_extra(extra)` lit
  `SourceConfig.extra["lint"]`.

### Registry de reporters (P1 #7/#8)

```python
REPORTERS = {"markdown": MarkdownReporter(), "json": JsonReporter()}
```

CLI : `--format json|markdown`. `LintReport.as_markdown()` a été
**supprimé** — anti-pattern d'import retardé. Le rendu passe par le
registry.

### Convention de nommage des rapports

`audit/<YYYY-MM-DD>__lint__<source>.md` (cf. ADR 0018). Les rapports
JSON vont dans `tools/output/lint/<source>/<date>__lint__<source>.json`.

### Auto-fix — hors scope P1.5

Le linter est **lecture seule**. Un hook `AutoFixableRule(LintRule)`
Protocol est *documenté* (cf. commentaire en bas de
`tools/lint/rules/base.py`) pour P2. Pas d'impl en P1.5.

### Sidecar per-entity — forward-compat

`tools/output/lint/<source>/<entity_id>.json` reste possible (gate UI
Phase 4). Non implémenté en P1.5 — la signature `JsonReporter` est
compatible.

### Méta-agrégateur — Phase 4

`--source all` itère sur `tools.config.registry.list_sources()` et
produit un rapport par source (P2 #15). Un `MetaLintReport` (somme
issues, top sources problématiques) est *prévu* en signature mais
non implémenté — cf. ADR 0016.

## Conséquences

**Positives** :

- Détection sur le vrai dataset (run 2026-06-10 *avant* CR senior) :
  832 issues, dont 751 (90 %) faux positifs `recommendedby_consistency`
  + 16/19 faux positifs `aberrant_values` (timestamps MM:SS).
- Run *après* CR senior C1/C3 : faux positifs massivement réduits
  (sentinels whitelistés, MM:SS = WARNING distinct, NFKC pour
  Unicode), exit code basé sur les ERROR *réels* unfiltered.
- Architecture testable à 100 % (couverture 100 % nouveau code).
- Substituable (DIP) : `LintService([SomeRule(), …])` + `DatasetLoader`
  Protocol substituable.
- Filtrage CLI sans biaiser l'exit code (H9).

**Négatives** :

- Reste des issues à instruire — tickets P1.6+ par règle.
- Le registry des règles est explicite (vs auto-discovery). Compromis
  assumé.
- Divergence Severity / Reporter cross-modules : dette technique
  documentée dans ADR 0017, convergence Sprint 2.

**Notes / jalons** :

- Auto-fix en P2 (Protocol `AutoFixableRule` documenté, pas implémenté).
- `tools/output/lint/<source>/<entity_id>.json` sidecars exposable
  pour la review UI Phase 4 — signature compatible.
- `MetaLintReport` à implémenter Phase 4.
- Convergence `tools/audit_core/` : Sprint 2 fin Phase 1 (ADR 0017).
