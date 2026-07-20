# ADR 0009 — Format JSON canonique des entités persistées

Date : 2026-06-10
Statut : Acceptée

## Contexte

La nouvelle couche `Item` / `Mention` (ADR 0001–0004) persiste un fichier
par entité dans `src/content/items/<source>/<id>.json` et
`src/content/mentions/<source>/<id>.json`. Sans politique d'encodage
explicite, deux outils peuvent produire le même contenu sémantique avec
des bytes différents (indent, ordre des clés, fin de ligne), créant des
diffs git polluants et cassant l'idempotence textuelle des `upsert`.

L'idempotence sémantique de `repository/_base.py::write_json_idempotent`
(C1) absorbe une partie du problème, mais ne suffit pas dès qu'un fichier
est édité à la main ou produit par un script tiers (ex. backups). Une
politique d'encodage **commune et applicable** rend ces incidents
impossibles.

## Décision

Tout fichier JSON persisté par un codec de cette couche DOIT respecter :

1. `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)` ;
2. terminer par **un seul** `\n` (POSIX, pas CRLF) ;
3. encodage UTF-8 sans BOM ;
4. champs `null` / collections vides : **omis** côté `to_dict` (cohérence
   avec Zod `.optional()` côté Astro).

## Mise en œuvre

- `repository/_base.py::write_json_idempotent` est le seul point d'écriture
  pour `ItemRepoJson` et `MentionRepoJson`. Il applique la règle.
- `common.atomic_write_text` gère le `\r` → `\n` côté Windows.
- Tout nouveau codec qui voudra court-circuiter ce helper DOIT documenter
  pourquoi en commentaire de tête de fichier.

## Conséquences

### Positives
- Diff git lisibles, atomiques, gérables manuellement si besoin (un
  `git diff` montre uniquement les changements sémantiques).
- Idempotence textuelle restaurée : `upsert(x); upsert(x)` ne ré-écrit
  pas — même après un round-trip par un éditeur externe respectant la
  politique.
- Pas de risque de drift entre OS (CRLF vs LF).

### Négatives
- `sort_keys=True` casse l'ordre déclaratif des codecs (mineur — l'ordre
  Astro est dicté par Zod, pas par le JSON).

### Neutres
- La règle ne s'applique pas aux fichiers legacy (`src/content/recos/`)
  qui suivent leur propre politique historique. Une migration éventuelle
  pourra les aligner.
