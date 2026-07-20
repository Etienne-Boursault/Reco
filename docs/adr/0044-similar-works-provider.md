# ADR 0044 — `SimilarWorksProvider` : frontière Python ↔ Astro pour les œuvres similaires

- **Statut** : Accepté
- **Date** : 2026-06-12
- **Auteurs** : Architecte P3.5-C
- **Liens** : ADR 0032 (page œuvre canonique), ADR 0033 (embeddings
  sémantiques)

## Contexte

La page canonique d'œuvre (`/<source>/oeuvre/<itemId>`, livrée P2.11)
affiche un bloc « œuvres similaires ». L'implémentation actuelle utilise
`similarByCreator` dans `src/lib/work/aggregator.ts` — un **placeholder**
purement basé sur l'égalité de créateur. Le pipeline d'embeddings (ADR
0033 / P2.15) produit des voisins cosinus de bien meilleure qualité,
mais n'est **pas câblé** à la page.

Contraintes :

1. Le site est **statique** (`output: 'static'`). Pas de SQLite à
   l'exécution côté navigateur, donc pas d'appel direct à
   `tools/embeddings/recommend.py` depuis Astro.
2. Le pipeline d'embeddings est **optionnel** : un fork peut tourner
   sans (ADR 0033 décrit `embed_items.py` comme étape distincte). La
   page œuvre **doit** continuer de fonctionner.
3. La frontière Python ↔ Astro est déjà bien établie (cf. ADR 0032,
   ADR 0035) : Python écrit des JSON sous `tools/output/` ou
   directement dans `src/content/`, Astro lit via les collections ou via
   `fs.readFile` au build.
4. Le bloc « similaires » doit pouvoir être **swappé** sans toucher au
   composant Astro (Open/Closed) : architecte, designer et data eng
   travaillent sur des axes différents.

## Décision

### Interface TypeScript (frontière)

Introduire `SimilarWorksProvider` dans `src/lib/work/similarity.ts` :

```typescript
export interface SimilarWork {
  id: string;
  title: string;
  score?: number; // cosine ∈ [-1, 1] si fourni par embeddings ; absent sinon
  reason: 'creator' | 'embeddings';
}

export interface SimilarWorksProvider {
  findSimilar(
    current: ItemLike,
    candidates: ItemLike[],
    opts?: { limit?: number },
  ): SimilarWork[];
}
```

Deux implémentations livrées :

- **`creatorBasedProvider`** — extrait de la fonction historique
  `similarByCreator` du module `aggregator.ts`. Logique inchangée
  (`reason='creator'`, pas de `score`).
- **`embeddingsBasedProvider(sourceId, dataLoader)`** — lit un JSON
  pré-généré (cf. infra). Si le JSON est absent pour l'item demandé,
  retourne `[]` (le composant tombe ensuite sur le creator-based).

### Sélecteur

```typescript
export function getSimilarWorksProvider(
  sourceId: string,
  opts?: { embeddingsDataDir?: string },
): SimilarWorksProvider;
```

Stratégie :

1. Si `opts.embeddingsDataDir` est fourni ET qu'au moins un fichier
   existe pour la source → retourne un **provider composite** :
   embeddings d'abord, fallback creator si embeddings retourne `[]`.
2. Sinon → `creatorBasedProvider` direct.

### Build-time export Python

Nouveau CLI : `tools/export_similar_works.py`

```
python tools/export_similar_works.py --source un-bon-moment [--k 6]
```

- Lit `tools/output/embeddings/embeddings.sqlite` (issu de
  `embed_items.py`).
- Pour chaque item : top-K voisins via `SimilarityRecommender.top_k`
  (réutilise l'existant — pas de duplication d'algorithme).
- Écrit `tools/output/similar_works/<source>.json` atomiquement
  (`atomic_write_text` + lockfile pipeline).
- Schéma :

  ```json
  {
    "schemaVersion": 1,
    "source": "un-bon-moment",
    "model": "<encoder model name>",
    "k": 6,
    "generated_at": "2026-06-12T10:00:00Z",
    "items": {
      "<itemId>": [
        { "id": "<otherId>", "score": 0.84 },
        ...
      ]
    }
  }
  ```

- Tests : mock store, vérifie JSON conforme + atomicité (pas de fichier
  partiel en cas d'erreur).

### Intégration build Astro

- Le fichier exporté est **gitignoré** (sous `tools/output/`). Au build,
  une copie ou un symlink le rend disponible sous
  `src/content/similar-works/<source>.json` **OU** la page le lit
  directement via `node:fs` (build-time only — pas servi au navigateur).
- Si le fichier est **absent** (déploiement sans embeddings) → le
  selector retourne `creatorBasedProvider`, l'expérience utilisateur
  dégrade gracieusement.
- **Phase 3.5 NE TOUCHE PAS** `src/pages/[source]/oeuvre/[itemId].astro`
  (Fixer P3.5-A en charge i18n actif sur ce fichier). Le câblage du
  composant à `getSimilarWorksProvider(sourceId)` est un follow-up de
  petite taille à faire après i18n.

### Rétro-compatibilité

`aggregator.ts` continue d'exporter `similarByCreator` (alias /
ré-export depuis `similarity.ts`). Aucun call-site existant à modifier
en Phase 3.5.

## Conséquences

### Positives

- **Open/Closed** : ajouter un futur provider (`hybrid`, `genre-based`,
  un service tiers) ne touche ni le composant Astro ni les autres
  providers.
- **Frontière nette** : Python possède l'algorithme (embeddings cosine),
  TypeScript possède le contrat de rendu — chacun testable
  indépendamment.
- **Graceful degradation** : un déploiement minimal (sans pipeline
  embeddings) fonctionne sans config, sans erreur silencieuse.
- **Réutilise l'existant** : pas de nouvel algo de similarité ; le CLI
  d'export est un wrapper fin sur `SimilarityRecommender`.

### Négatives / limites

- Duplication mineure de la liste « top-K voisins » côté JSON et côté
  SQLite — choix assumé pour éviter de servir SQLite côté frontend.
  Taille estimée : ~30 KB / 1000 items / K=6 (négligeable).
- Le JSON est **régénéré explicitement** (CLI), pas en `npm run build`.
  CI peut l'invoquer en pre-build si embeddings.sqlite existe.
- Phase 3.5 ne câble pas le composant ; le bénéfice utilisateur arrive
  au prochain ticket.

### Critères de revisite

- Si l'on ajoute du cross-source ou de la similarité multi-modale →
  réviser le schéma JSON et le contrat `SimilarWork`.
- Si le JSON dépasse 1 MB par source → splitter par item
  (`<source>/<itemId>.json`) ou compresser.

## Liens

- Code TS : `src/lib/work/similarity.ts`,
  `src/lib/work/aggregator.ts` (ré-export `similarByCreator`).
- Code Python : `tools/export_similar_works.py`.
- Tests : `tests/work/test_similarity.test.ts`,
  `tests/test_export_similar_works.py`.
