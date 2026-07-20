# ADR 0007 — Politique transactionnelle de la migration en 2 phases strictes

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

`MigrationService.migrate(dry_run=False)` écrit pour chaque reco source
deux fichiers : un Item et une Mention. La séquence naïve "boucle (item,
mention) écrits ensemble" pose un problème en cas de **crash partiel**
(OSError, kill, panne disque) :

- Si on écrit `mention[i]` avant `item[i]`, un crash entre les deux
  laisse une **mention orpheline** qui pointe vers un item absent. Le
  site Astro plante alors au build (référence cassée).
- Si on écrit `item[i]` puis `mention[i]`, un crash entre laisse un
  **item orphelin** : pas de mention le référence. C'est inoffensif —
  Astro ne génère pas de page pour un Item sans Mention.

Le service ne possède **pas** de transaction native (pas de DB) :
chaque upsert est atomique (rename POSIX) mais l'ensemble ne l'est pas.

## Décision

**2 phases strictes** dans `MigrationService.migrate()` :

1. **Phase 1 — Items** : itérer sur tous les `(item, _)` parsed et
   upserter `item_repo.upsert(item)`. Dédoublonner par `item.id` en
   mémoire (plusieurs mentions du même item → 1 seul upsert).
2. **Phase 2 — Mentions** : une fois la phase 1 entièrement terminée,
   itérer sur tous les `(_, mention)` parsed et upserter
   `mention_repo.upsert(mention)`.

Invariants garantis :

- **Aucune mention orpheline n'est jamais persistée** (la phase 2 ne
  commence qu'après la fin de la phase 1).
- Un crash entre les phases laisse des items orphelins (acceptable).
- Un crash *pendant* la phase 2 laisse des mentions partiellement
  écrites, toutes valides (chaque mention écrite référence un item
  déjà persisté).
- Idempotence : ré-exécuter `migrate()` après un crash reprend là où ça
  s'est arrêté (les upserts sont idempotents).

## Politique d'erreurs

- **Parse fail-fast** : une reco mal formée est loggée dans
  `stats.errors` et skipped. Le run continue.
- **Write best-effort** : un upsert qui échoue (OSError) est loggé en
  erreur ; le run continue avec les recos suivantes.
- **Distinction stat** : `n_errors` (problèmes bloquants) vs
  `n_warnings` (signaux : items orphelins, drift verify deep).

## verify() est l'autorité de cohérence post-migration

Quatre contrôles :

1. Chaque reco source a une mention persistée (`mention manquante`
   si non).
2. Chaque mention pointe vers un item existant (`item orphelin` si non).
3. Items persistés sans mention qui les référence → **warning**.
4. Deux items distincts avec même `canonical_key` → **erreur**.

Mode `verify(deep=True)` : re-parse chaque reco source et compare le
canonical_key obtenu à celui de l'item persisté. Détecte les dérives
silencieuses (ex. quelqu'un a édité un item.json manuellement).

## Conséquences

- Positives :
  - Robustesse face aux crashs : pas de site Astro cassé après une
    migration interrompue.
  - Pas de rollback complexe à implémenter (on relance, c'est tout).
  - `verify()` complet permet de débloquer la phase suivante avec
    confiance.
- Négatives :
  - Doit garder en mémoire tous les `parsed: list[(Item, Mention)]`
    avant la phase 1 (overhead : ~2866 paires × ~5 KB = ~14 MB,
    acceptable).
  - Phase 1 + Phase 2 séparées doublent le nombre de syscalls de
    `stat()` ; impact négligeable face au IO.
- Notes :
  - Quand on passera à un backend SQLite, ces phases se résumeront à
    une seule transaction. L'API publique de `migrate()` reste stable.
