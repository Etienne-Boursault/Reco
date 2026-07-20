# ADR 0002 — `Item.types` reste un tuple multi-typage

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

L'entité `Item` (œuvre référencée) expose `types: tuple[ItemType, ...]` plutôt
qu'un seul `type: ItemType`. Le CR archi a remonté l'incohérence suivante :

- `canonical_key(title, creator, types)` intégrait les `types` triés dans la
  clé → deux items représentant la même œuvre mais avec un `types` différent
  (ex. `(FILM,)` vs `(FILM, SERIES)`) n'avaient jamais la même clé.
- `ItemIdentityService.find_match` vérifiait pourtant l'intersection des
  types, supposant des clés potentiellement identiques côté caller.
- `can_merge_items` reposait sur la même clé → deux items mergeables d'après
  l'intersection des types pouvaient être déclarés incompatibles.

## Décision

1. `Item.types` reste un **tuple** d'`ItemType` (multi-typage explicite —
   exemple réel : une adaptation est à la fois `FILM` et `LIVRE` ; un manga
   est à la fois `BD` et `SERIES`).
2. `canonical_key(title, creator)` **n'intègre plus les `types`** dans la
   clé. La clé identifie l'œuvre par titre + créateur normalisés
   uniquement. Les types sont traités séparément.
3. `find_match` compare la clé canonique **ET** vérifie l'intersection
   non vide des types (logique inchangée — devient cohérente).
4. `can_merge_items` compare la clé canonique **ET** vérifie l'intersection
   non vide des types **ET** vérifie la compatibilité des `external_ids`.

## Conséquences

- Les 3 fonctions (`canonical_key`, `find_match`, `can_merge_items`) sont
  désormais alignées.
- Un test existant qui vérifiait que `types=(FILM,)` et `types=(SERIES,)`
  étaient non-mergeables doit être ré-interprété : ils sont désormais
  rejetés non pas par la clé canonique, mais par l'intersection vide des
  types — le résultat externe reste identique (`False`).
- La signature `canonical_key(title, creator, types)` change en
  `canonical_key(title, creator)`. Comme le code n'est pas encore appelé
  par les couches IO (Phase 1 item 2.A vient juste de livrer), aucune
  régression externe n'est attendue. Une compatibilité ascendante (param
  `types` optionnel, ignoré avec `DeprecationWarning`) est conservée.
- ADR 0003 (typed-identity / `BookIdentity` / `FilmIdentity`) reste différé.
