# ADR 0043 — Façade unifiée recherche lexicale + sémantique

- **Statut** : Accepté
- **Date** : 2026-06-12
- **Auteurs** : Architecte P3.5-C
- **Liens** : ADR 0020 (cache FTS5), ADR 0033 (embeddings sémantiques),
  ADR 0035 (search frontend MiniSearch)

## Contexte

Phase 2 a livré deux moteurs de recherche complémentaires mais **disjoints** :

- **Lexical** (ADR 0020 / P2.8) — `SearchService` côté Python, basé sur
  FTS5 (`tools/search/service.py`). BM25 natif, exact match, robuste sur
  les noms propres et codes courts.
- **Sémantique** (ADR 0033 / P2.15) — `SemanticSearchService` côté Python
  (`tools/search/similarity.py`), basé sur embeddings cosine. Catch les
  reformulations, paraphrases, intentions floues.

Chacun a son angle mort :

| Cas | Lexical | Sémantique |
|-----|---------|------------|
| « parasite » → film de Bong Joon-ho | OK | OK |
| « film sur les inégalités sud-coréen » | KO | OK |
| « kaamelott » (typo absente du corpus) | KO | partiel |
| « 808 » (code court) | OK | bruit |

Les consommateurs (CLI review, future page `/recherche` enrichie, futurs
endpoints `/_data/search/*.json`) doivent pouvoir interroger un seul
point d'entrée qui orchestre les deux backends.

ADR 0035 a explicitement **différé** la fusion (« Si on ajoute un index
sémantique, une 2ᵉ couche pourra venir en sus … mais reste hors scope de
ce ticket. »). Phase 3.5 lève cette dette **côté Python uniquement** ;
l'intégration frontend (palette Cmd+K, `dist/search.json` enrichi) reste
un item Phase 4.

## Options envisagées

### A. Weighted blend `α·lex + (1-α)·sem`

Demande de normaliser les deux scores (FTS5 BM25 vs cosine ∈ [-1, 1]) —
calibration fragile, varie par requête. α devient un hyperparamètre à
tuner par source.

### B. Reciprocal Rank Fusion (RRF) — **retenue**

`score(d) = Σ 1 / (k + rank_i(d))` où `i` parcourt les backends et
`rank_i(d)` est le rang du document dans la liste de l'engine i (∞ si
absent). `k=60` (constante recommandée par Cormack et al. 2009).

Avantages :

- **Aucune normalisation** des scores natifs — RRF ne consomme que les
  rangs.
- **Robuste** aux échelles hétérogènes (BM25 borné > 0, cosine ∈ [-1, 1]).
- **Implémentation triviale** (~30 lignes), zéro dépendance.
- État de l'art utilisé par Elasticsearch, OpenSearch, Vespa pour la
  fusion hybride.

### C. Learning-to-rank (LTR) ML

Hors scope absolu Phase 3.5 (corpus de jugements de pertinence inexistant).

## Décision

Implémenter `UnifiedSearchService` dans `tools/search/unified.py` :

```python
class UnifiedSearchService:
    def __init__(
        self,
        lexical: SearchService,
        semantic: SemanticSearchService | None,
    ) -> None: ...

    def search(
        self,
        query: UnifiedQuery,
    ) -> tuple[UnifiedHit, ...]: ...
```

avec :

- `UnifiedQuery(text, source_id, strategy, limit)` — frozen dataclass.
- `UnifiedStrategy ∈ {LEXICAL_ONLY, SEMANTIC_ONLY, HYBRID}` (StrEnum).
  Défaut : `LEXICAL_ONLY` (rétro-compat avec le comportement actuel).
- `UnifiedHit(id, source_id, lexical_rank, semantic_rank, combined_score)`
  — `*_rank` optionnel (None si absent du backend), `combined_score`
  toujours présent.
- Backend sémantique **injecté optionnellement** : si `None` (déploiement
  sans `embeddings.sqlite`), `HYBRID` retombe gracieusement sur
  `LEXICAL_ONLY`.
- RRF constante `k=60` (constante module, modifiable mais documentée).
- Tie-break déterministe par `id` ascendant (tests reproductibles).

### Frontière sémantique vs lexical

- **Lexical** opère sur items + episodes (cf. `SearchService.search`).
- **Sémantique** opère seulement sur items (P2.15 n'embed pas les
  épisodes — l'index sémantique est par œuvre).
- En `HYBRID`, on fusionne **par scope** : items combinent lex+sem,
  épisodes restent purement lex. `UnifiedHit.kind` distingue
  (`"item" | "episode"`).

### Périmètre Phase 3.5

- Implémentation Python pure + tests unitaires (mocks backends).
- **NE PAS** modifier `src/pages/search.json.ts` ni la palette Cmd+K
  (`src/components/SearchPalette.astro`) — ADR 0035 reste in-place,
  fusion frontend = item Phase 4.
- **NE PAS** modifier l'endpoint `/recherche` actuel.
- L'intégration build-time (générer `dist/_data/search-unified.json`) est
  un futur ticket conditionné par le besoin produit (palette filtrable
  par mode lexical/sémantique).

## Conséquences

### Positives

- Point d'entrée unique pour les consommateurs Python (CLI review,
  scripts d'audit, futures pages Astro statiques générées au build).
- Couplage faible : `SearchService` et `SemanticSearchService` injectés
  via leurs interfaces existantes (DIP) — testable avec mocks.
- RRF est **stateless** et **anytime** — aucun pré-calcul, aucune
  invalidation à orchestrer.
- Graceful degradation : un déploiement sans embeddings (ADR 0033 est
  optionnel) ne casse pas la façade.

### Négatives / limites

- RRF ignore la **magnitude** des scores (un hit BM25=42 et un hit
  BM25=2 ont le même apport si même rang). En pratique : acceptable, car
  les hits forts arrivent en tête → faible rank → fort RRF.
- Pas encore de fusion côté épisodes (P2.15 ne les couvre pas) — affiché
  comme limitation connue.
- Mesure de qualité différée : pas de banc d'évaluation A/B en
  Phase 3.5 ; sera ajoutée si l'on adopte la façade côté frontend
  (Phase 4+).

### Critères de revisite

- Si l'on construit un banc d'évaluation (jugements de pertinence
  manuels sur 50+ requêtes) → comparer RRF vs weighted-blend tuné.
- Si la palette frontend adopte un mode « intent search » → exporter un
  JSON dédié et reconsidérer la stratégie par défaut (`HYBRID` ?).
- Si embeddings couvrent les épisodes → étendre la fusion au scope
  `episodes`.

## Liens

- Code : `tools/search/unified.py`
- Tests : `tests/search/test_unified.py`
- Référence : Cormack, Clarke, Buettcher, *Reciprocal Rank Fusion
  outperforms Condorcet and individual Rank Learning Methods*, SIGIR
  2009.
