# ADR 0033 — Embeddings sémantiques (dédup cross-épisode + recos similaires)

* Statut : Accepté (Phase 2 Vague 2A — item roadmap #15)
* Date : 2026-06-11
* Décideurs : Dev P2.15 (ML/backend)
* ADR liés : 0019 (audit-core), 0020 (cache SQLite + FTS5 — §P2-7 mentionne
  la table sœur `items_embeddings`), 0024 (CI quality gates).

## Contexte

Deux besoins convergent en Phase 2/3 :

1. **Dédup cross-épisode**. Le pipeline d'extraction génère parfois deux
   items distincts pour la même œuvre quand le titre est exprimé
   différemment d'un épisode à l'autre (cas canonique : *Le Tombeau des
   lucioles* vs *Grave of the Fireflies* — cf. mémoire projet). La
   normalisation lexicale (`normalize_text`) ne suffit pas. Il faut un
   signal sémantique pour proposer à l'humain des fusions probables.
2. **Recos similaires**. Phase 3 prévoit un widget « continue le voyage »
   et des suggestions ML. FTS5 (P2.8) répond aux *recherches*
   lexicales — pas aux *similarités latentes* (genre, ambiance,
   thématique). Un embedding par item permet un top-K cosinus.

Le kit Reco est **self-hostable** : pas de clé API, pas de service
externe obligatoire. Les ADR 0024 et 0028 imposent que la phase
pipeline reste reproductible sans compte payant.

## Décision

1. **Modèle d'embeddings : `BAAI/bge-small-en-v1.5`** via
   [`fastembed`](https://github.com/qdrant/fastembed) (ONNX, CPU).
   * dim 384, ~50 MB de poids, ~5 ms/embed CPU, multilingue acceptable
     pour titres+créateurs+types (qualité FR à étalonner).
   * Alias roadmap : `all-MiniLM-L6-v2` (même dim, qualité comparable —
     bascule possible sans changer le schéma).
2. **Persistance dans une table sœur SQLite** dédiée (séparée du cache
   `tools/output/cache.sqlite`, cf. ADR 0020 §P2-7) :

   ```sql
   CREATE TABLE items_embeddings (
     source_id   TEXT NOT NULL,
     id          TEXT NOT NULL,
     model       TEXT NOT NULL,
     dim         INTEGER NOT NULL,
     vector      BLOB NOT NULL,   -- numpy float32 packed
     embedded_at TEXT NOT NULL,
     source_hash TEXT NOT NULL,   -- sha256(input_text) pour invalidation
     PRIMARY KEY (source_id, id)
   );
   CREATE INDEX idx_embeddings_model ON items_embeddings(model);
   ```

   * Chemin par défaut : `tools/output/embeddings/embeddings.sqlite`
     (gitignored).
   * Schéma versionné via `embeddings_meta.embeddings_schema_version`.
3. **Input à embedder** : `title | creator | types_joined |
   description_tronquée` (256 char max). Le `quote` est exclu (souvent
   générique, casse la similarité).
4. **Algorithme dédup** : O(n²) brute sur la matrice normalisée. Seuil
   par défaut : **0.85**. Borne pratique : 10 000 items
   (≈100 M comparaisons, ≈1 s numpy). Au-delà : bascule FAISS HNSW.
5. **API publique** : `tools/search/similarity.py` expose
   `SemanticSearchService` (façade homogène avec le FTS5 P2.8 —
   l'API reste *complémentaire*, pas de fusion automatique encore).
6. **CLI** : `tools/embed_items.py` — idempotent via `source_hash`,
   `--dry-run`, `--force`, `--export-dedup-json`. Tient le
   `pipeline_lock` (cf. `review_lock`) pendant l'écriture.

## Architecture

```
tools/embeddings/
  __init__.py
  ports.py        # Protocols Encoder + EmbeddingStorePort (DIP)
  encoder.py      # EmbeddingInput, build_input_text, FastEmbedEncoder
  store.py        # EmbeddingStore (SQLite)
  similarity.py   # cosine_similarity, normalize_rows, top_k
  dedup.py        # CrossEpisodeDedup
  recommend.py    # SimilarityRecommender
tools/embed_items.py        # CLI
tools/search/similarity.py  # Façade publique (SemanticSearchService)
```

Tous les algorithmes (dedup, recommend, CLI) dépendent EXCLUSIVEMENT des
Protocols `Encoder` et `EmbeddingStorePort`. Les tests injectent un
`FakeEncoder` déterministe (SHA-256 → vecteur) — **jamais** de download
fastembed en CI.

## Alternatives écartées

* **OpenAI `text-embedding-3-small`** (dim 1536). Rejeté : nécessite une
  clé API → casse le kit self-hostable (ADR 0028). Coût ~ 0.02 $/1M
  tokens — non bloquant techniquement mais bloquant philosophiquement.
* **Multilingual E5 large** (dim 1024). Meilleure qualité FR/EN à
  étalonner, mais 2× plus lent (~10 ms/embed CPU) et ~500 MB de poids.
  À reconsidérer si les seuils de dédup MiniLM produisent trop de faux
  positifs sur corpus FR mixte (cf. *Critères de bascule*).
* **FAISS HNSW** dès maintenant. Overkill <10 k items — brute O(n²)
  numpy est plus simple, déterministe, sans dépendance C++. Réserve à
  Phase 3+ si scale.
* **Pas d'embeddings** (uniquement FTS5 + normalize_text). Insuffisant
  pour dédup cross-langue (« Tombeau » vs « Grave ») et pour les recos
  thématiques (FTS5 ignore le sens).
* **Stocker les embeddings dans le cache principal** (`cache.sqlite`).
  Rejeté : couplage du cycle de vie (rebuild cache ≠ ré-embed,
  invalidations indépendantes), cf. ADR 0020 §P2-7.

## Conséquences

### Positives

* Self-hostable, déterministe pour un modèle donné.
* Schéma SQLite isolé : un rebuild de cache (P2.8) ne touche pas aux
  embeddings, et inversement.
* Idempotence : `source_hash` filtre les re-encodages inutiles ;
  changement de modèle = ré-encodage forcé naturel.
* Pipeline lock partagé avec `extract_recos` / `enrich_*` : pas de
  course d'écriture sur les items pendant l'embedding.
* Façade `SemanticSearchService` analogue à `SearchService` (P2.8) —
  intégration simple côté Astro/handlers.

### Négatives

* Dépendance optionnelle `fastembed` (~80 MB onnxruntime + modèle).
  Lazy-import : les tests et les scripts qui n'embedent pas n'en ont
  besoin.
* O(n²) dédup borne le passage à l'échelle (~10 k items/source).
  Au-delà : bascule HNSW (FAISS ou hnswlib).
* La qualité FR de MiniLM/BGE-en n'est pas étalonnée sur le corpus
  Reco — un suivi (faux positifs/négatifs sur 100 paires labellisées
  humain) est nécessaire avant d'activer une fusion auto.

## Critères de bascule

* **Vers E5-large multilingual** : si > 20 % de faux positifs à
  seuil 0.85 sur un échantillon FR-EN labellisé.
* **Vers FAISS HNSW** : si une source dépasse 10 k items OU si le
  recompute dédup dépasse 5 s par source.
* **Vers index intégré au cache** : si les invalidations
  embeddings/cache convergent (rebuild systématique des deux).

## Métriques baseline (run dry-run, 2026-06-11)

* Source `un-bon-moment` : **2 651 items** candidats.
* Coût d'encodage estimé (MiniLM CPU, batch 64) : ~15 s pour 2 651 items.
* Taille DB attendue : 2 651 × (384 × 4 octets vecteur + overhead) ≈
  4 MB.
* Run CLI : `python tools/embed_items.py --source un-bon-moment --dry-run`.

## Tests

`tests/embeddings/` + `tests/test_embed_items_cli.py` — 91 tests,
**100 % de couverture** sur `tools/embeddings/*`, `tools/embed_items.py`,
et `tools/search/similarity.py`. Mock `FakeEncoder` partagé via
`tests/_embed_fakes.py` — aucun téléchargement modèle en CI.

## Addendum — Settings injectables (P3.5-B, 2026-06-12)

Dette Phase 2.5 reportée : les défauts (model, batch_size, dedup_threshold,
db_path) étaient hardcodés dans ``argparse``. Aligne ``embed_items`` sur
le pattern ``enrich_audit``/``match_audit``/``lint`` (ADR 0019, SSOT).

- **Nouveau** : ``tools/embeddings/settings.py`` — ``EmbeddingsSettings``
  (frozen, slots) avec ``from_source_extra(extra, overrides=...)``
  déléguant à ``audit_core.settings.from_source_extra``.
- **Champs** : ``model_name``, ``batch_size``, ``dedup_threshold`` (∈ [-1, 1]),
  ``db_path`` (Path, coerce depuis str), ``desc_max_chars``
  (forward-compat ; encoder utilise actuellement sa constante interne).
- **CLI inchangée** : ``--model``, ``--batch-size``, ``--dedup-threshold``,
  ``--db`` restent des overrides au-dessus des défauts ``Settings``.
- **Tests** : ``tests/embeddings/test_settings.py`` (17 tests TDD).

Forward-compat : quand le CLI sera scindé par source (P4+), un fork
pourra ajuster ``batch_size`` ou ``dedup_threshold`` par source via
``src/content/sources/<source>.json`` (clé ``extra.embeddings``).

## Liens

* Roadmap item #15 (Embeddings sémantiques).
* Mémoire : *Nettoyage collisions* (justifie la dédup cross-épisode).
* ADR 0020 §P2-7 (origine de la décision « table sœur, pas FTS »).
