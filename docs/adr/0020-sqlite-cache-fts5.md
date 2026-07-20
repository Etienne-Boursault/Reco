# ADR 0020 — Cache d'index SQLite + FTS5 (read-through depuis JSON)

- Statut : **Acceptée — implémentée** (Phase 2 Vague 1, P2.8, livraison 2026-06-10)
- Date : 2026-06-10
- Décideurs : équipe Reco
- ADRs liés : 0001 (architecture multi-source), 0019 (audit_core)

## Contexte

Phase 1 clôturée avec ~2651 items, 2866 mentions et 104 épisodes (source
`un-bon-moment`). La vision 5-10 podcasts × 1000+ épisodes × 20k+ recos
arrive ; deux opérations deviennent coûteuses :

1. **Lookup par champ non-clé** (e.g. « tous les items recommandés par
   Hakim Jemili ») — actuellement, parcours linéaire du dossier
   `mentions/<source>/` à chaque requête : 2866 ouvertures de fichier.
2. **Recherche full-text** (titre item, hôtes/invités d'épisode,
   `recommendedBy`) — fonctionnalité prévue pour le site public (#9) et
   le reviewer (filtres).

Options évaluées :

| Option | Pour | Contre |
|---|---|---|
| **In-memory dict + regex** | Zéro dépendance, simple | Ne scale pas à 20k+ ; pas de BM25 ; rebuild à chaque démarrage |
| **Whoosh** (Python pur) | Index FTS dédié | 5-10× plus lent que FTS5 ; mainteneur instable |
| **Meilisearch** (server) | Très bon ranking, fuzzy | Server externe = friction kit déployable ; overkill pour <100k docs |
| **SQLite + FTS5** | Zéro-dep (stdlib), BM25 natif, atomic builds, file-based | Single-writer (acceptable : build périodique mono-process) |

## Décision

Introduire `tools/cache/` (builder/reader/schema/fts) et `tools/search/`
(SearchService au-dessus du reader) avec stratégie **read-through depuis
JSON** :

1. **Source de vérité** : les JSON sous `src/content/{items,mentions,episodes}/`
   restent canoniques. Le cache SQLite est dérivé, jetable, regénérable.
2. **Build atomique** : `<db>.tmp` → `os.replace`. Aucun lecteur ne voit
   un fichier partiel.
3. **FTS5** virtual tables `items_fts` / `episodes_fts` avec tokenizer
   `unicode61 remove_diacritics 2` (essentiel pour le FR).
4. **Read-through** : `CacheReader.get_item_or_rebuild(...)` vérifie la
   `mtime` du JSON ; si stale, déclenche un refresh incrémental (un seul
   item) via le builder injecté.
5. **DIP** : `JsonLoader` Protocol pour les tests, `CacheBackend`
   Protocol pour une bascule future éventuelle (Meilisearch si on
   franchit le seuil ci-dessous).

CLI : `tools/build_cache.py --source <id>|all [--force] [--vacuum]`
sous lockfile pipeline.

## Conséquences

**Positives**

- Zéro dépendance externe (sqlite3 stdlib, FTS5 compilé par défaut sur
  CPython Windows/macOS/Linux récents).
- Build complet `un-bon-moment` (2651 items + 2866 mentions + 104 ep) :
  ~87s sur disque local Windows ; cache 2.13 MiB.
- Recherche FTS5 : ~1000 qps en charge (query `film`, limit=10), <4ms
  par requête typique.
- Tests 100% couverture sur `tools/cache/`, `tools/search/`,
  `tools/build_cache.py` (97 tests). Pas de mocks (filesystem éphémère).
- API immutable (`@dataclass(frozen=True, slots=True)`,
  `MappingProxyType` sur `external_ids`).

**Négatives**

- Rebuild complet obligatoire sur changement de `CACHE_SCHEMA_VERSION`
  (mitigation : versioning explicite + `cache_meta`).
- Single-writer (un seul `build_cache.py` à la fois) — acceptable, géré
  par `acquire_pipeline_lock`.
- Le read-through ne couvre que le cas item : pour épisodes/mentions on
  s'appuie sur un rebuild complet périodique (build_cache CLI au démarrage
  du dev / déploiement).
- Surcoût mémoire négligeable (2 MiB), mais la base est en
  `tools/output/` donc hors `src/content/` — bien gitignorée.

**Critères de bascule** (Meilisearch / Typesense)

Revisiter cette ADR si **au moins une** des conditions suivantes est
remplie :

- Volume > 100k recos OU > 50k épisodes (FTS5 reste rapide mais l'index
  augmente).
- > 5 sources actives avec ranking inter-sources critique (boost par
  source, personnalisation).
- Besoin de **fuzzy matching** natif (typo-tolerance) — FTS5 prefix `*`
  ne couvre que les préfixes.
- Besoin de facetting riche (filtres combinatoires) côté site public.

Tant qu'aucun critère n'est rempli : SQLite reste le bon choix
(simplicité, zero-ops, atomic builds).

## Notes d'implémentation

- Tokenizer : `unicode61 remove_diacritics 2` — variante 2 retire les
  diacritiques en plus de l'unicode normalization (essentiel pour FR :
  « coréen » match « coreen »).
- `fts_query` sanitize l'entrée utilisateur : strip des opérateurs FTS5
  (`AND`/`OR`/`NOT`/`NEAR`), wrap chaque token entre `"..."*` pour
  prefix matching + protection injection.
- BM25 ranking : `rank` ASC (FTS5 retourne des scores négatifs, le plus
  négatif étant le plus pertinent).
- `items_fts` contient `title` + `GROUP_CONCAT(DISTINCT recommended_by)`
  des mentions + `GROUP_CONCAT(DISTINCT guests_parsed)` des épisodes
  liés ; cela permet de chercher un item via le nom de l'invité qui l'a
  recommandé OU le nom d'un invité présent dans l'épisode (utile pour
  les recos prononcées par l'invité).
