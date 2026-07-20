# ADR 0010 — Versioning de schéma & migrations versionnées

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

Les entités du domaine (`Item`, `Mention`, `SourceConfig`) sont
persistées en JSON-on-disk (`src/content/{items,mentions,sources}/...`).
Elles portent un champ `schemaVersion: int = 1` introduit en P1.2.

Sans mécanisme de migration explicite, tout changement non rétro-
compatible (renommage de champ, restructuration) condamnerait à :

- soit éditer manuellement des milliers de fichiers JSON (erreur garantie),
- soit casser le pipeline à la lecture (compat ad-hoc dans chaque codec).

Options envisagées :

1. **Migration ad-hoc à la lecture** (style ORM "lazy upgrade"). Rejet :
   pollue les codecs, rend l'audit du dataset opaque (impossible de
   savoir si un champ a été migré ou s'il était d'origine).
2. **Script unique par changement** (style `migrate_recos_to_item.py`).
   Rejet : ne capitalise pas — chaque nouvelle migration repart de zéro,
   pas d'auto-discovery, pas de chaînage.
3. **Mécanisme fichier-par-migration + runner** (style Alembic light).
   **Retenu**.

## Décision

Mise en place de `tools/migrations/` avec auto-discovery :

```
tools/migrations/
  __init__.py
  registry.py            # SSOT des entités versionnées, discovery
  runner.py              # MigrationRunner + Protocol Migration + MigrationStats
  item/
    v1_to_v2.py          # une classe `V{X}To{Y}Migration` par module
  mention/
    v1_to_v2.py
  source/
    v1_to_v2.py
```

Contrat (`Protocol`) :

```python
class Migration(Protocol):
    SOURCE_VERSION: int        # version de départ
    TARGET_VERSION: int        # version d'arrivée (= SOURCE_VERSION + 1)
    ENTITY: str                # "item" | "mention" | "source"
    def migrate_one(self, data: dict) -> dict: ...  # pure, no IO
```

Principes :

- **SRP** : chaque module = une transition v_X → v_X+1.
- **OCP** : ajouter une migration = créer un nouveau fichier, **zéro
  modification** du runner ou du registry.
- **DIP** : `MigrationRunner` consomme les migrations via le Protocol,
  pas via import direct.
- **Forward-only** : pas de `migrate-down`. Rationale : on n'a jamais
  eu besoin de rollback en prod, et l'asymétrie réduit la surface de
  bugs (cf. ADR 0009 — JSON canonique).

### Pourquoi `schemaVersion` par entité (pas global)

Un `schemaVersion` global forcerait à bumper toutes les entités
ensemble même si une seule change. Par-entité permet d'évoluer
chaque agrégat à son rythme — aligné sur DDD (un schéma par
agrégat).

### Auto-discovery via `importlib`

`registry._discover_all_migrations(entity)` :

1. importe `migrations.{entity}` (chargement paresseux),
2. itère via `pkgutil.iter_modules` sur les fichiers du sous-package,
3. ne retient que les noms matchant `^v(\d+)_to_v(\d+)$`,
4. introspecte chaque module pour trouver l'unique classe terminant
   par `Migration` dont l'attribut `ENTITY` matche.

Coût : O(N_migrations) à chaque `discover_migration_chain` (peu
fréquent — appelé une fois par run CLI). Pas de cache nécessaire
en Phase 1.

### CLI : `tools/migrate_schema.py`

```bash
python tools/migrate_schema.py --entity item --to-version 2 \
    --source un-bon-moment --dry-run        # défaut
python tools/migrate_schema.py --entity item --to-version 2 \
    --source un-bon-moment --apply           # écrit
```

- Acquiert `review_lock.acquire_pipeline_lock` (refuse si le serveur
  tourne, sauf `--ignore-server-lock`).
- Dry-run par défaut — `--apply` explicite pour écrire (UX safe).
- Sortie JSON sur stdout (parsing CI / piping).
- Codes retour :
  - `0` : succès,
  - `2` : argparse (entité/source_id invalide),
  - `3` : `UnknownEntityError` / `UnsupportedTargetVersionError`,
  - `4` : `PipelineLockBusy` / `ServerLockBusy`.

## Template — ajouter une migration future v2 → v3

1. Bumper `Item.schema_version` (ou `Mention`/`SourceConfig`) côté
   domaine — le constructeur force `>= 2`.
2. Créer `tools/migrations/item/v2_to_v3.py` :

   ```python
   class V2ToV3Migration:
       SOURCE_VERSION = 2
       TARGET_VERSION = 3
       ENTITY = "item"
       def migrate_one(self, data):
           if int(data.get("schemaVersion", 1)) != self.SOURCE_VERSION:
               raise ValueError(...)
           out = dict(data)
           # … transformation métier ici …
           out["schemaVersion"] = self.TARGET_VERSION
           return out
   ```

3. Ajouter ses tests sous `tests/test_migrations_item_v2_to_v3.py`
   (TDD strict, 100 % couverture).
4. Le `MigrationRunner` la picke automatiquement — aucun autre code à
   modifier. Le CLI démontre : `--to-version 3 --apply`.

## Cohabitation supprimée

L'ancien placeholder `tools/domain/migrations.py` (registre interne
`register`/`migrate`) a été supprimé en P1.3 — il faisait double-emploi
avec `tools/migrations/` et créait deux SSOT pour la même responsabilité.
Un import régressif lève désormais `ImportError` (cf. test
`test_domain_migrations_module_is_removed`).

## Atomicité

Deux niveaux à distinguer :

### Par fichier — garantie

Chaque écriture passe par `common.atomic_write_text` (écrit dans `.tmp`,
fsync, rename). Conséquence : soit le fichier sur disque est
**intégralement** à `target_version`, soit il est **intact** à sa
version précédente. Aucune écriture intermédiaire n'est jamais
persistée.

Si une étape intermédiaire de la chaîne v_N → v_{N+1} → v_{N+2} lève
(p. ex. la migration v2→v3 plante alors que v1→v2 a réussi en mémoire),
**rien** n'est écrit pour ce fichier — il reste à `current_version` sur
disque. Le fichier est comptabilisé en `n_errors`, le run continue sur
les autres fichiers.

### Multi-fichiers (globale) — best effort

Un `kill -9`, panic ou crash matériel mid-run peut laisser le dataset
hétérogène (certains fichiers à `target_version`, d'autres à
`current_version`).

Mitigation immédiate : ré-exécuter le runner. Il est **idempotent** —
les fichiers déjà migrés sont skip (cf. `n_skipped`). On reprend
exactement là où le crash s'est produit.

Mitigation future éventuelle (YAGNI tant qu'on n'a pas de cas réel) :
option `--backup-dir <path>` qui copie tous les fichiers source avant
mutation et offre un rollback bulk.

## Politique côté repository (lazy vs fail-fast)

Question pour les futures versions ≥ 2 : que doit faire le repository
si on lit un fichier à `schemaVersion < CURRENT_VERSION` ?

- **Lazy upgrade** : migrer à la volée en mémoire (sans écrire), exposer
  l'objet en v_courante. Pro : zéro flag day, pas besoin de migrer le
  dataset. Con : code de lecture pollué, audit opaque.
- **Fail-fast** : refuser, exiger d'avoir lancé `migrate_schema.py
  --apply` avant. Pro : SSOT du dataset, audit clair. Con : un déploiement
  oublié casse le serveur.

**Décision Phase 1** : fail-fast — le repository assume que le dataset
est à `CURRENT_VERSION[entity]`. À reconsidérer si on industrialise
plusieurs déploiements concurrents.

## Conséquences

- **Positives** :
  - capitalise sur un seul mécanisme — chaque migration est isolée et
    testée unitairement (pureté garantie par le `Protocol`).
  - dry-run par défaut → impossible d'écrire le dataset par erreur.
  - idempotent — re-run = no-op si déjà migré.
  - fail-soft : un fichier corrompu est comptabilisé en `n_errors`,
    pas un crash.
  - chaîne validée à la découverte (saut/trou → `InvalidMigrationChainError`).
  - `MigrationStats.observed_from_versions` documente le mix de versions
    rencontrées (audit fin sans regrep sur 10k fichiers).
- **Négatives** :
  - léger overhead d'`importlib` au startup du CLI (négligeable, ms,
    et caché via `lru_cache` après le 1er appel).
  - le `Protocol` ne capture pas la pureté côté types — convention.
- **Notes** :
  - Pas de rollback (forward-only). Si un jour nécessaire, ajouter
    `migrate_back` au Protocol et un sous-mode `--rollback` au CLI.
  - Pour l'instant les 3 migrations existantes sont des **no-op
    placeholders** (`v1 → v2` ne change rien). Sert de template — la
    Phase 1 ne fait pas de breaking change métier.
  - Séparation engine pur / runner IO : voir ADR 0011.
