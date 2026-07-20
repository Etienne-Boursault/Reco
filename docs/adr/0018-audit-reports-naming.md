# ADR 0018 — Convention de nommage des rapports d'audit

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco
- ADR liés : 0012 (linter), 0013 (match audit), 0014 (enrich audit), 0017 (doctrine)

## Contexte

Avant cette ADR, le linter écrivait dans `audit/<YYYY-MM-DD>.md`. Deux
sous-systèmes d'audit (lint + match) lancés le même jour s'écrasaient
mutuellement, et il n'y avait pas de moyen rapide de trouver le
rapport « lint de la source X au 10 juin ». Les rapports historiques
deviennent illisibles dès qu'on ajoute une nouvelle source.

## Décision

Convention de nommage **unique** pour tous les rapports d'audit :

```
audit/<YYYY-MM-DD>__<scope>__<source>.<ext>
```

- `<scope>` ∈ { `lint`, `match`, `enrich`, `meta` }
- `<source>` = slug de la source (ex. `un-bon-moment`).
- `<ext>` ∈ { `md`, `json`, `jsonl` }.

Exemples :
- `audit/2026-06-10__lint__un-bon-moment.md`
- `audit/2026-06-10__match__un-bon-moment.md`
- `audit/2026-06-10__enrich__un-bon-moment.json`

### Rapports JSON

Les rapports JSON sont écrits sous `tools/output/<scope>/<source>/`
plutôt que dans `audit/` pour ne pas polluer le dossier humain :

```
tools/output/lint/un-bon-moment/2026-06-10__lint__un-bon-moment.json
```

### `audit/INDEX.md`

Régénéré best-effort par chaque run (non-bloquant), indexe les
rapports présents et les groupe par scope. (Implémentation : Sprint 2,
juste l'esquisse documentée ici.)

### Anti-collision

- L'écrasement reste *par défaut* (le rapport quotidien est idempotent
  sur le même dataset).
- Flag `--no-overwrite` côté CLI : ajoute un suffixe horaire
  `__<HHMMSS>` si la cible existe (utile pour comparer deux runs
  successifs).

## Conséquences

**Positives** :
- Plus de collisions entre sous-systèmes / sources.
- Tri lexical = tri chronologique + scope + source.
- Glob `audit/*__lint__*` retrouve tous les lints.

**Négatives** :
- Migration douce : les anciens rapports `audit/<date>.md` restent
  lisibles mais ne suivent pas la nouvelle convention. Pas de
  renommage automatique (pas critique — les humains s'adaptent).
- Path plus long. Compromis assumé.

## Notes

- Le linter (P1.5) **applique** cette convention dès cette PR.
- `match_audit` et `enrich_audit` migreront dans une PR dédiée Sprint 2.
- `meta` est réservé au futur méta-agrégateur (cf. ADR 0016).
