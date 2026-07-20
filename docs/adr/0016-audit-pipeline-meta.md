# ADR 0016 — Pipeline d'audit unifié (meta-pattern)

- Statut : Proposée — **Superseded by ADR 0019** (`audit_core/` unifié)
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

Au terme de la Phase 1, on a fait éclore **trois modules d'audit**
indépendants :

- `tools/match_audit/` (P1.6) — audit du match Episode ↔ vidéo YouTube ;
- `tools/enrich_audit/` (P1.7) — audit du match Item ↔ payload TMDB ;
- `tools/lint/` (P1.5) — lint structurel du dataset.

Chacun a son `Suspicion`, sa `Severity` (ou son `score` numérique), son
`Check` (Callable libre ou `Protocol`), son `cli_runner`, ses
`reporters/`. Le pattern est très similaire mais l'implémentation diverge.

À court terme c'est sain (on apprend par module ce qui marche). À moyen
terme, ça crée :

- friction cognitive (l'humain doit re-comprendre chaque module) ;
- duplication de validation (3 modules définissent leur propre
  `Severity`) ;
- risque d'incohérences sémantiques (un même verdict peut s'exprimer
  différemment selon le module).

## Décision

On **documente le meta-pattern** sans le forcer immédiatement. La conver-
gence concrète (extraction d'un `tools/audit_common/`) est **reportée fin
Phase 1**, une fois les trois modules stabilisés et leurs cas d'usage
clos.

### Conventions à respecter dans les futurs modules `<X>_audit/`

1. **VOs partagés** (à terme via `audit_common.types`) :
   - `Suspicion(kind: str, detail: str, severity: Severity, confidence:
     float | None = None)` — frozen, slots, validation à la construction.
   - `Severity = StrEnum(INFO < WARNING < CRITICAL)` — convention naturelle
     « élevé = grave », `value` lowercase pour sérialisation JSON.
   - `Check(Protocol)` — `name`, `kind`, `description`, `__call__(entity,
     external_data) -> Suspicion | None`. Les fonctions libres exposent
     ces attributs en `# type: ignore[attr-defined]` (rétro-compat).
   - `AuditResult` et `SourceAuditReport` par module (couplage fort à
     l'orchestration locale).

2. **Layout par module** :
   ```
   tools/<X>_audit/
     __init__.py
     types.py          ← VOs locaux + ré-exports de audit_common
     thresholds.py     ← Final constants, source unique
     service.py        ← orchestration, isolation try/except par check
     cli_runner.py     ← RunOptions + run_audit (testable sans subprocess)
     providers.py      ← fabriques d'IO injectables
     reporters/        ← markdown_reporter, json_reporter, jsonl_reporter
     <check>_check.py  ← 1 check par module, Pure
   tests/<X>_audit/
     test_<chaque module>.py
     test_corpus_reference.py   ← calibration, 20+ cas étiquetés
   ```

3. **Conventions CLI** (`tools/<X>_audit.py` ou `tools/audit_<x>.py`) :
   - Dry-run **par défaut**, `--apply` seul flag écrivant. Le drapeau
     `--dry-run=True` n'existe pas (CR senior C1).
   - Codes de sortie : `0` = OK, `1` = erreur fatale, `2` =
     `--fail-on-suspect` et suspects détectés.
   - Lock global pipeline via `acquire_pipeline_lock(force=...)`.
   - Seuils principaux exposés en flags CLI dédiés.
   - Reporter `markdown`/`json`/`none` ; option `--jsonl-log` séparée.
   - `--undo-last` quand l'écriture est destructive
     (cf. archive→restore d'`enrich_audit`).

4. **Idempotence** :
   - Tout horodatage écrit doit être **injectable** (param de fonction,
     pas `datetime.now()` côté module). Permet sha256-equal sur deux
     runs.
   - Toute opération `clear` doit être **archive** par défaut (réversible)
     ; option `archive=False` pour les tests.

5. **Sidecar vs in-place** (CR senior M2) :
   - **Entité pure** (Item, œuvre, source) → **sidecar versionné**
     dans `tools/output/<X>_audit/<id>.json` avec `schemaVersion`,
     `auditorVersion`, `auditedAt`. Pas de bump schema_version de
     l'entité — Zod tolère un champ optionnel forward-compat.
   - **Relation** (Episode = (source, vidéo YT) ; Mention = (item,
     épisode)) → **flag in-place** dans le JSON de la relation. L'info
     appartient naturellement au lien.

6. **Isolation des erreurs** : chaque check tourne dans un try/except.
   Un check qui lève n'arrête pas l'audit ; on incrémente un compteur
   dédié (`skipped_check_error`) tracé dans le rapport.

7. **Calibration** : un module sans `test_corpus_reference.py` à 20+ cas
   étiquetés n'est **pas bon pour prod**. Le test est bloquant ; il
   capture précisément ce qui se passe quand on bouge un seuil.

### Critères de bascule vers `audit_common/` (concret)

- ≥ 3 modules livrés et stables (✔ : lint, match_audit, enrich_audit) ;
- la duplication de code de `Severity`/`Check` Protocol est > 50 lignes
  cumulées ;
- au moins un test cross-module nécessite des VOs communs.

Quand les trois critères sont remplis : créer un PR dédié « unify audit
VOs » avec extraction mécanique (mv + ré-export shim 1 sprint, puis
suppression des shims).

## Conséquences

### Positives

- **Pas de gros refactor sous pression** : chaque module termine sa
  Phase 1 sur ses propres rails.
- **Convention écrite** : le prochain module d'audit (Spotify ? Music-
  Brainz ?) suit le template sans inventer son propre vocabulaire.
- **Sidecar vs in-place clarifié** : on tranche la fausse incohérence
  ressentie entre `match_audit` et `enrich_audit`.

### Négatives

- **Duplication temporaire** : 3 `Severity`/`Suspicion` parallèles. C'est
  un dette assumée, court-bornée par les critères de bascule.
- **Pas de typing partagé** côté IDE — un dev qui touche les 3 modules
  doit re-comprendre les VOs locaux. Compensé par la documentation
  centrale ici.

### Notes

- Convergence visée : **fin Phase 1**, dans un PR dédié « audit_common ».
- Si un 4ᵉ module d'audit apparaît avant la convergence, ne pas attendre
  : extraire `audit_common.types` immédiatement.
