# ADR 0019 — `audit_core/` unifié

- Statut : **Acceptée — implémentée** (Sprint 2 Phase 1, livraison 2026-06-10)
- Date : 2026-06-10
- Décideurs : équipe Reco
- Supersede : ADR 0016 (méta pipeline) + ADR 0017 (doctrine convergence)
- ADRs liés : 0012 (linter), 0013 (match audit), 0014 (enrich audit),
  0015 (sidecar match)

## Contexte

Au terme de la Phase 1 et après la livraison de P1.5/P1.6/P1.7, trois
sous-systèmes d'audit cohabitent :

- `tools/lint/` (P1.5) — lint structurel ;
- `tools/match_audit/` (P1.6) — audit Episode ↔ vidéo ;
- `tools/enrich_audit/` (P1.7) — audit Item ↔ TMDB.

ADR 0016 documentait le meta-pattern. ADR 0017 documentait la doctrine de
convergence reportée Sprint 2. La CR cumulative cross-modules a confirmé
que les trois axes critiques peuvent être unifiés sans casse :

1. **Severity** divergente (cf. tableau ci-dessous).
2. **Reporter Protocol** : 3 implémentations quasi-identiques avec
   `_md_escape` / `_escape_md` / `escape_md` divergents (S-03).
3. **`_safe_segment` sidecar** : `match_audit` laxiste vs `enrich_audit`
   strict (S-01).
4. **`from_source_extra`** : factorisé deux fois (`match_audit/settings.py`
   + `lint/settings.py`).
5. **`cli_runner`** : 3× boilerplate (lock, audited_at, RunOptions).
6. **`Severity`** : 3 enums différentes.

## Décision

Créer `tools/audit_core/` avec les modules suivants :

| Module                          | Responsabilité                                                |
|---------------------------------|---------------------------------------------------------------|
| `audit_core/types.py`           | `Severity` (4 niveaux), `Suspicion` base, `Check` Protocol.   |
| `audit_core/settings.py`        | `from_source_extra(extra, key, cls, overrides)` factorisé.    |
| `audit_core/sidecar.py`         | `_safe_segment` strict (modèle enrich_audit), helpers atomic. |
| `audit_core/reporters.py`       | `Reporter` Protocol + `escape_md` union complète.             |
| `audit_core/cli_runner.py`      | `RunOptions[Ctx, Report]` générique + helpers locks.          |
| `audit_core/trail.py`           | `JsonlAuditTrail`, `NoopAuditTrail`, archive/restore.         |

### Option retenue pour `Severity` : **option B — 4 niveaux unifiés**

```python
class Severity(StrEnum):
    INFO     = "info"
    WARNING  = "warning"
    ERROR    = "error"
    CRITICAL = "critical"
```

Justification : zéro casse de sérialisation.

| Module          | État avant   | Mapping vers `audit_core.Severity`        |
|-----------------|--------------|-------------------------------------------|
| `lint`          | E/W/I        | `ERROR→ERROR`, `WARNING→WARNING`, `INFO→INFO` |
| `match_audit`   | E/W          | `ERROR→ERROR`, `WARNING→WARNING`           |
| `enrich_audit`  | I/W/C        | `INFO→INFO`, `WARNING→WARNING`, `CRITICAL→CRITICAL` |

Les sidecars existants (sérialisation `"warning"`, `"error"`, `"critical"`)
restent valides à la lecture (StrEnum value-compatible).

### `_safe_segment` : modèle strict `enrich_audit`

Regex `^[a-z0-9][a-z0-9._-]{0,63}$` + rejet NUL + rejet noms réservés
Windows (`con`, `prn`, `aux`, `nul`, `com1..9`, `lpt1..9`). Le laxisme de
`match_audit.sidecar._safe` est aligné dessus — pas de cas connus
incompatibles dans le dataset `un-bon-moment` (les `episode_id` sont des
ULIDs/hex).

### `escape_md` : union complète

Caractères échappés : `\`, `*`, `_`, `` ` ``, `[`, `]`, `|`, `\n`, `\r`.
Préfixé par un `\` (markdown standard).

### `Reporter` Protocol

```python
class Reporter(Protocol):
    format_id: str  # "markdown" | "json" | "none"
    def render(self, report: Any) -> str: ...
```

Pas d'héritage requis — duck typing structurel.

### `cli_runner.RunOptions[Ctx, Report]`

```python
@dataclass(frozen=True)
class RunOptions(Generic[Ctx, Report]):
    source_id: str
    audited_at: str
    fail_on_suspect: bool
    mode: Literal["apply", "dry-run"]
    output_format: Literal["markdown", "json", "none"]
    # Modules sous-classent pour ajouter `items`, `provider`, etc.
```

### VOs locaux préservés

`LintIssue`, `MatchSuspicion`, `Suspicion` (enrich_audit) **restent dans
leurs modules**. `audit_core.Suspicion` est une base utilisable par
composition — l'héritage n'est pas imposé.

## Critères de bascule chiffrés

| Condition                              | Action                          |
|----------------------------------------|---------------------------------|
| Coverage `audit_core/` < 100%          | Bloquer merge                   |
| Régression suite 2576+ tests           | Bloquer merge                   |
| Diff sidecar avant/après migration     | Doit être vide sur `un-bon-moment` |
| Nouvel ADR par module supplémentaire   | Pas requis (audit_core absorbe) |

## Conséquences

### Positives

- **Une SSOT** pour `Severity`, `Reporter`, `escape_md`, `_safe_segment`,
  `from_source_extra`. Suppression de ~600 lignes dupliquées attendue.
- **DRY** : ajouter un 4e module d'audit (Spotify/MusicBrainz) ne duplique
  plus rien.
- **Convergence rétro-compat** : aucune sidecar existante invalidée.

### Négatives

- **Migration coûteuse** (3 modules à toucher, 2576 tests à garder verts).
  Plannifiée Sprint 2 fin Phase 1 sur PR dédiée.
- **Risque d'over-engineering** si `audit_core` devient un cimetière
  d'abstractions. Mitigation : tout ce qui est dans `audit_core` doit avoir
  ≥ 2 consommateurs réels.

## Plan de migration

1. Créer `tools/audit_core/` + tests 100% (PR #1).
2. Migrer `lint/` (PR #2) — 1 module à la fois pour limiter le diff.
3. Migrer `match_audit/` (PR #3).
4. Migrer `enrich_audit/` (PR #4).
5. Supprimer les duplications dans chaque module (PR #5).
6. Mettre à jour ADR 0019 : "Acceptée — implémentée".

## Statut Fixer cumulatif Phase 1 (2026-06-10)

Le Fixer cumulatif livre :
- l'**ADR 0019** (ce document) — décision actée et plan tracé,
- la **supersession** de 0016 et 0017,
- la **correction factuelle** des Severity dans 0017.

L'**implémentation** d'`audit_core/` est **reportée Sprint 2** car son
coût (≥ 5 PRs, migration 3 modules, 2576 tests à garder verts) dépasse le
budget d'un fix cumulatif unitaire. Aucune régression n'est introduite ;
les 3 modules continuent de fonctionner dans leur shape actuelle.

## Statut livraison Sprint 2 (2026-06-10)

`audit_core/` est livré et les 3 modules migrés :

### Livré

- **`tools/audit_core/`** (7 modules) — 100% de couverture, 88 tests dédiés.
  - `types.py` : `Severity` 4-niveaux StrEnum, `Suspicion` base, `Check`
    Protocol, `coerce_severity`, `severity_rank`, `severity_value`.
  - `settings.py` : `from_source_extra(extra, key, cls, overrides, tuple_fields)`
    générique.
  - `sidecar.py` : `_safe_segment` strict (modèle enrich_audit) +
    `ensure_output_within` anti-traversal.
  - `reporters.py` : `Reporter` Protocol + `escape_md` union complète
    (`\, *, _, backtick, [, ], |, \n→space, \r→space`).
  - `cli_runner.py` : `RunOptionsBase[Ctx, Report]` générique + `utcnow_iso`.
  - `trail.py` : `JsonlAuditTrail`, `NoopAuditTrail`, `AuditTrail` Protocol.

- **`tools/lint/`** :
  - `rules/base.py:Severity` réexporte `audit_core.types.Severity`
    (option B — `INFO`/`WARNING`/`ERROR` accessibles + `CRITICAL` nouveau).
  - `settings.py:LintSettings.from_source_extra` délègue à
    `audit_core.settings.from_source_extra`.
  - `reporters/markdown_reporter.py:_escape_md` réexporte
    `audit_core.reporters.escape_md` (gagne `|`, `\n`, `\r`).

- **`tools/match_audit/`** :
  - `types.py:Severity` réexporte `audit_core.types.Severity`
    (option B — `INFO`/`CRITICAL` accessibles en plus de `ERROR`/`WARNING`).
  - `settings.py:MatchAuditSettings.from_source_extra` délègue à
    `audit_core.settings.from_source_extra`.
  - `sidecar.py:_safe` délègue à `audit_core.sidecar._safe_segment`
    (whitelist stricte remplace le pattern laxiste — S-01).
  - `sidecar.py:write_sidecar` ajoute `schemaVersion: 1` (R-01) ;
    `read_sidecar` accepte les sidecars legacy sans schemaVersion avec
    un warning log (rétro-compat).
  - `cli_runner.py:_md_escape` délègue à `audit_core.reporters.escape_md`
    (gagne `\, *, _, backtick, [, ], \n, \r` en plus de `|` — S-03).

- **`tools/enrich_audit/`** :
  - `types.py:Severity` réexporte `audit_core.types.Severity` (object identity
    avec les autres modules).
  - `flag_writer.py:_safe_segment` réexporte
    `audit_core.sidecar._safe_segment` (sémantique inchangée — déjà strict).
  - `reporters/markdown_reporter.py:_md_escape` réexporte
    `audit_core.reporters.escape_md` (gagne `*`, `_`, `[`, `]`).
  - **Nouveau** `settings.py:EnrichAuditSettings` (D-01/V-01) —
    `EnrichAuditSettings.from_source_extra(extra, overrides=None)`
    permet désormais de configurer les seuils depuis
    `SourceConfig.extra["enrich_audit"]`.
  - `cli_runner.py:default_service` accepte un `settings:
    EnrichAuditSettings | None = None` ; les kwargs historiques
    (`title_threshold`, `year_tolerance`, `film_min_runtime`) restent
    overrides au call-site.

- **`src/content.config.ts`** : enum Zod
  `matchSuspectReasons[].severity` élargi de `['error', 'warning']` à
  `['info', 'warning', 'error', 'critical']` (forward-compat — T-04).

- **Tests inter-modules** :
  - `tests/test_severity_legacy_sidecars.py` (7 tests) — couvre la
    lecture rétro-compat des sidecars match_audit v0 (sans
    schemaVersion), inter-op Severity 4-niveaux, object identity des
    réexports `Severity`.

### Reporté Sprint 3 (compromis acceptable, cf. plan Fixer)

- **Dette-6 / Dette-11** : extension first-class de `SourceConfig` avec
  `match_audit: MatchAuditConfig | None` et `enrich_audit:
  EnrichAuditConfig | None`. Risque élevé sur la chaîne
  `astro_adapter → normalize_payload → schema validation` (≥ 6 fichiers
  de tests cross-stack). La lecture via `extra["match_audit"]` et
  `extra["enrich_audit"]` fonctionne déjà, sans casse.

- **T-01 / T-03** : tests cross-modules `test_dual_sidecars_read` et
  `test_cli_exit_codes_uniform` — P3, hors budget Sprint 2.

### Régressions

Aucune. Suite cible : **2576 baseline → 2683 passants** (107 nouveaux
tests, 0 fail). Couverture `audit_core` : 100%.
