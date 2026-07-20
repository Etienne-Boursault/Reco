# ADR 0015 — Pattern sidecar pour les verdicts d'audit de match

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco
- Numérotation : ADR 0014 ayant été pris par `enrich_audit`, le pattern
  sidecar de `match_audit` est documenté ici en 0015.

## Contexte

ADR 0013 a posé `matchSuspect: boolean` directement dans le JSON
d'épisode. Pratique pour Astro (un badge ↔ un flag), mais ça :

1. **Pollue le domaine éditorial** avec un détail d'audit
   (signature/score/severity) qu'un fork du projet n'a pas
   nécessairement envie d'exposer côté UI.
2. **N'est pas extensible** : ajouter une 4e raison (ex. embedding
   sémantique Phase 2) impose une bump de `schemaVersion` à chaque
   évolution.
3. **N'est pas réversible facilement** : un `--apply` réécrit les JSON
   d'épisode et il n'y a aucun audit trail pour annuler en cas
   d'erreur.

`enrich_audit` (ADR 0014) a tranché côté **sidecar** : un fichier JSON
par verdict dans `tools/output/enrich_audit/<source>/<item>.json`,
domaine pur, jetable, extensible. On aligne `match_audit` sur la même
stratégie.

## Décision

### Sidecar = source de vérité du verdict détaillé

Layout disque :

```
tools/output/match_audit/<source>/<slugify(guid)>.json
tools/output/match_audit/<source>/_run_<timestamp>.jsonl   ← audit trail
```

Schéma sidecar (ordre des clés préservé, indent=2, pas de sort_keys) :

```json
{
  "episodeGuid": "abc123",
  "matchSuspect": true,
  "suspicions": [
    {"kind": "duration_mismatch", "detail": "diff 23.4%", "severity": "error"},
    {"kind": "title_drift",       "detail": "0.21 < 0.3", "severity": "warning"}
  ],
  "auditedAt": "2026-06-10T12:34:56Z"
}
```

### Le JSON d'épisode conserve un miroir bool

Pour que le badge Astro reste trivial à brancher, le JSON d'épisode
reçoit toujours un `matchSuspect: true` (jamais `false` — on retire le
champ pour garder le JSON minimal). Le **détail** des suspicions vit
EXCLUSIVEMENT dans le sidecar.

Le schéma Astro accepte aussi (forward-compat, non peuplé par P1.6) :

- `matchSuspectReasons: { kind, detail, severity }[]`
- `matchSuspectAuditedAt: string`

Un futur job d'agrégation pourra populer ces champs depuis les sidecars
sans bumper le schemaVersion (déjà optional).

### Audit trail JSONL pour --apply

À chaque `--apply`, un fichier `_run_<UTC_iso_no_punct>.jsonl` est créé
dans le dossier sidecar de la source. Une ligne par événement
(`match_audit.flag`, `match_audit.sidecar`). Le `--undo-last` relit le
dernier trail pour :

- retirer le flag `matchSuspect` posé,
- supprimer les sidecars écrits,
- consommer le trail (unlink).

### Convention de chemin transcript (CR senior C3/C4)

Pour éviter qu'un faux fallback `<slug>.txt` partagé soit lu à la fois
comme Acast et comme YouTube (et produise un faux "intro identique"),
on fige la convention :

```
tools/output/transcripts/<source>/<slugify(guid)>.acast.txt
tools/output/transcripts/<source>/<slugify(guid)>.youtube.txt
```

Plus aucun fallback `.txt` n'est lu par `FileTranscriptRepo`. Un fichier
absent → le check intro skippe silencieusement (cf. CR senior H9 :
pas de fallback `""` qui masquerait un bug pipeline).

## Conséquences

### Positives

- **Domaine épisode pur** : seul un booléen est exposé côté JSON ;
  Astro consomme un flag binaire et c'est tout.
- **Extensible** : ajouter une 4e suspicion = ajouter une entrée dans le
  tableau sidecar, zéro migration.
- **Réversible** : `--undo-last` couvre l'erreur humaine "j'ai
  `--apply` avec les mauvais seuils".
- **Idempotence stricte** : le flag_writer N'utilise PAS `sort_keys=True`
  (qui aurait réordonné les clés au premier `--apply` et cassé
  l'idempotence sur tous les épisodes existants).

### Négatives / Compromis assumés (cumulatifs Phase 1)

- **Duplication value objects** avec `enrich_audit` (Suspicion, Severity,
  AuditResult, SourceAuditReport). La convergence (`audit_core`) est
  REPORTÉE à la fin de Phase 1 : extraire un module commun exigerait
  d'éditer simultanément `enrich_audit` (zone interdite par
  coordination multi-agents). Coût : ~80 lignes dupliquées ; bénéfice
  du report : aucun conflit de merge entre agents P1.6 et P1.7.
- **`match_youtube.py` réimplémente `title_match_score` localement**.
  L'extraction d'une fonction publique partagée est REPORTÉE Sprint 3
  (zone hors scope P1.6).
- **`SourceConfig.match_audit` section** : lue via `extra["match_audit"]`
  pour ne pas casser la couche P1.1 (autre agent). Une extension
  officielle du schéma `SourceConfig` est à programmer en Phase 1
  cumulative.
- **`pyproject.toml` entry-point** : reporté (non bloquant — le hack
  `sys.path` a été supprimé du CLI puisque `pyproject.toml` configure
  déjà `pythonpath = ["tools"]`).
- **Embedding sémantique Phase 2** : `IntroSimilarityStrategy` Protocol
  préparé, seul `SequenceMatcherStrategy` implémenté.

## Validation

- Tests unitaires + d'intégration sur le mapping
  `provider → transcript file path` (CR senior C4) — convention
  `<slugify(guid)>.{acast,youtube}.txt` testée.
- Couverture 100 % sur les fichiers nouveaux/modifiés.
- ADR 0013 mis à jour avec un "Suivi" pointant ici.
