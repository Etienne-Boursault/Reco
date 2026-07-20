# ADR 0011 — Harness d'évaluation de l'extraction de recos

- Statut : Acceptée (révisée 2026-06-10 post-CR archi + senior)
- Date initiale : 2026-06-10
- Décideurs : équipe Reco

## Contexte

Le pipeline d'extraction de recos repose sur un LLM (Haiku / Sonnet /
GPT-4o-mini). À chaque changement de prompt, de modèle, de température
ou de la stratégie de chunking, on ne sait pas dire **objectivement** si
on a régressé ou progressé. Tout repose sur des sondages manuels.

Conséquences :
- Pas de garde-fou pour merger un changement de prompt.
- Pas d'historique mesurable des modèles.
- Aucune métrique partageable pour arbitrer coût vs qualité.

Options examinées :
1. **Golden set figé + harness precision/recall/F1**.
2. **Bench auto-généré** (LLM-judge). Plus rapide à construire mais
   circulaire : un LLM juge un LLM.
3. **A/B blind sur l'UI review**. Plus proche du UX réel, mais lent et
   sans baseline reproductible.

## Décision

On retient l'option 1 : un **golden set figé annoté à la main**,
combiné à un **harness** qui calcule precision, recall et F1.

### Architecture (révision post-CR)

```
tools/eval/
  __init__.py
  types.py             # ExtractedReco, EvalConfig, EvalDetail,
                       # EvalMetrics, RunManifest,
                       # ExtractionSource & EvalReporter (Protocols),
                       # ReportFormat (StrEnum), constantes Final.
  golden_set.py        # ExpectedReco, GoldenEpisode, GoldenSet,
                       # load_golden_set, golden_set_hash.
  fuzzy_match.py       # normalize_text (NFKC+casefold+Unicode-aware),
                       # fuzzy_match_score (config-injectable).
  assignment.py        # linear_sum_assignment (Hungarian pur Python).
  metrics.py           # MatchVerdict, precision/recall/f1,
                       # f1_inclusive_ts, EvalResult (compat legacy).
  harness.py           # EvalHarness, DictExtractionSource,
                       # evaluate_full (per-episode).
  adapters/
    legacy_reco_adapter.py  # tools.domain._legacy.Reco → ExtractedReco.
  reporters/
    base.py            # Protocol EvalReporter + REPORTERS registry.
    csv_reporter.py    # CsvReporter + render_csv/write_csv.
    markdown_reporter.py
tools/eval_extraction.py    # CLI : run + compare.
tests/eval/golden_set/      # 3 fixtures synthétiques.
```

**Hors scope** du harness : tout appel LLM. L'extraction est faite
ailleurs et sérialisée en JSON (ou exposée via un ``ExtractionSource``
custom). Le harness consomme cette abstraction.

### Schéma d'annotation

```json
{
  "episode_guid": "abc123",
  "source_id": "un-bon-moment",
  "annotator": "etienne",
  "annotated_at": "2026-06-10T10:00:00Z",
  "expected_recos": [
    {
      "title": "Drive",
      "creator": "Nicolas Winding Refn",
      "types": ["film"],
      "timestamp": "00:34:12",
      "timestamp_tolerance_sec": 30,
      "recommended_by": "Navo",
      "kind": "reco",
      "must_have": true,
      "notes": "Évoqué pendant les films noirs"
    }
  ]
}
```

### Classification (révisée)

Pairing **optimal** expected ↔ extracted via Hungarian (assignment
problem). Cf. ``tools/eval/assignment.py``.

| Verdict | Condition | Décompte |
|---|---|---|
| `EXACT_MATCH` | score = 1.0 + timestamp ok | TP |
| `FUZZY_MATCH` | score ≥ seuil + timestamp ok | TP |
| `WRONG_TIMESTAMP` | score ≥ seuil mais timestamp ko | **bucket séparé** |
| `MISSED` / `MISSING_GOLD` | aucune correspondance ≥ seuil | FN |
| `SPURIOUS` / `EXTRA_PREDICTED` | extraction non appariée | FP |

`MISSED` et `MISSING_GOLD` sont synonymes — on garde `MISSED` en sortie
par défaut (compat legacy) ; `MISSING_GOLD` est exposé pour la
sémantique explicite réclamée par la CR senior (H1). Idem
`SPURIOUS`/`EXTRA_PREDICTED`.

### Invariant comptable (résolution C1)

Trois options ont été examinées pour le bucket `WRONG_TIMESTAMP` :

1. **TP plein** : un mauvais timestamp = un succès. Surévalue la qualité
   perçue côté UX (l'utilisateur clique sur un timestamp aberrant).
2. **FP** : un mauvais timestamp = une extraction incorrecte. Sous-évalue
   la qualité titre.
3. **Bucket séparé** (retenu) : `WRONG_TIMESTAMP` n'est compté ni en TP
   ni en FP/FN dans `precision/recall/f1`. On expose
   `f1_inclusive_ts(...)` (TP pondéré ×0.5) à des fins de débogage.

Formules officielles :

```
TP = n_exact_match + n_fuzzy_match
FP = n_spurious
FN = n_missed
precision = TP / (TP + FP)
recall    = TP / (TP + FN)
f1        = 2·P·R / (P + R)
```

`n_wrong_timestamp` est reporté dans le manifest et le rapport sans
peser sur le score principal — la décision (durcir, ignorer, accepter)
est laissée à l'humain en relecture du rapport.

### Assignment optimal (résolution C2)

`scipy.optimize.linear_sum_assignment` n'est **pas** une dépendance
projet (scipy absent du venv). On implémente donc le Hungarian
(Kuhn-Munkres O(n³)) en pur Python dans `tools/eval/assignment.py`,
API mimant scipy : `linear_sum_assignment(cost, maximize=False)`.

Trade-off accepté : O(n³) → suffisant pour les golden sets visés
(< 100 expected × < 100 extracted par épisode). Si scipy devient une
dépendance opt-in, on pourra basculer derrière un try/except sans
toucher au harness.

### CLI strict (résolution C3)

`tools/eval_extraction.py --strict-guid` : échoue (exit 2 + stderr)
si un épisode du golden set n'a pas de guid mappable côté
`--extracted`. Mode opt-in pour ne pas casser les usages "audit
partiel".

### Configuration injectable (résolution H6, M4)

Toute valeur numérique (seuil fuzzy, tolérance ts, bonus/malus créateur)
est centralisée dans `EvalConfig` (frozen). Constructeur `EvalConfig
.from_dict` prêt pour un chargement YAML/JSON futur.

Constantes par défaut :

| Constante | Valeur |
|---|---|
| `DEFAULT_FUZZY_THRESHOLD` | `0.85` |
| `DEFAULT_TIMESTAMP_TOLERANCE_SEC` | `5` |
| `DEFAULT_CREATOR_BOOST_THRESHOLD` | `0.8` |
| `DEFAULT_CREATOR_PENALTY_THRESHOLD` | `0.4` |
| `DEFAULT_CREATOR_BOOST` | `0.1` |
| `DEFAULT_CREATOR_PENALTY` | `0.15` |

NB : `ExpectedReco.timestamp_tolerance_sec` (par golden set, défaut
`30`) peut être supérieur à `EvalConfig.timestamp_tolerance_sec`
(global, défaut `5`). Le harness prend le **max** des deux, pour
respecter l'annotation manuelle plus permissive sans interdire de
durcir globalement.

### Abstraction ExtractionSource (résolution archi #1, #7)

Le harness consomme un Protocol `ExtractionSource` :

```python
class ExtractionSource(Protocol):
    def for_episode(self, episode_guid: str) -> Iterable[ExtractedReco]: ...
    def episode_guids(self) -> Iterable[str]: ...
```

Implémentations fournies :
- `DictExtractionSource` : depuis `{guid: [dict, ...]}`.
- `LegacyRecoExtractionSource` : depuis `tools.domain._legacy.Reco`.

Tout nouveau format (DB, API, parquet) = un nouveau dataclass
implémentant le Protocol, sans toucher au harness.

### RunManifest (résolution archi #2)

Chaque run produit un `RunManifest(frozen=True)` persisté en JSON sous
`tools/output/eval/runs/<run_id>.json` via `atomic_write_text`. Contenu :

```json
{
  "run_id": "2026-06-10T14-22-31",
  "timestamp": "2026-06-10T14:22:31+00:00",
  "git_sha": "abc123...",
  "config_hash": "fde81d2a...",
  "golden_set_hash": "ba9f3e...",
  "scores": {"precision": 0.83, "recall": 0.71, "f1": 0.77, ...},
  "sources": ["un-bon-moment"]
}
```

**Déterminisme** : `timestamp` est **injecté** (paramètre CLI
`--timestamp`) — pas de `datetime.now()` au point d'usage. Si non
fourni, défaut `now(UTC)` mais le manifest reste reproductible si on
re-passe le même timestamp.

Sous-commande `compare` :

```
python tools/eval_extraction.py compare \
    --base  tools/output/eval/runs/<run_id_base>.json \
    --target tools/output/eval/runs/<run_id_target>.json
```

Affiche un tableau markdown delta precision / recall / F1.

### Registre REPORTERS (résolution archi #3)

```python
# tools/eval/reporters/base.py
REPORTERS: dict[str, type] = {}

def register_reporter(name: str):
    def decorator(cls):
        REPORTERS[name] = cls
        return cls
    return decorator
```

Le CLI consomme `REPORTERS` via `--format <name>`. Ajout d'un format =
nouveau module qui s'enregistre via `@register_reporter("xml")`, sans
toucher au CLI ni au harness. OCP respecté.

Formats supportés (cf. `ReportFormat` StrEnum) : `csv`, `markdown`.

### Format CSV (résolution M3)

`csv.DictWriter` + `quoting=QUOTE_MINIMAL`, séparateur `,`, encodage
**UTF-8 BOM** (`utf-8-sig`) à l'écriture pour Excel-friendliness. Deux
sections : `# summary` (1 ligne) puis `# details`.

### Format Markdown (résolution M8)

Sections :
- Résumé global (Precision/Recall/F1, comptes).
- Si `EvalMetrics.per_episode` non-vide : Top-5 et Bottom-5 épisodes
  par F1.
- Détails par-reco (verdict, attendue, matchée, score).

### Log JSONL (résolution M5)

`EvalHarness(emit_jsonl=True)` émet des événements JSON via le logger
`reco` (cf. `tools/common.log`). Schéma événement :

```json
{
  "event": "eval.compare",
  "episode_guid": "ep1",
  "n_expected": 5, "n_extracted": 5,
  "n_exact": 3, "n_fuzzy": 2, "n_missed": 0,
  "n_spurious": 0, "n_wrong_ts": 0,
  "precision": 1.0, "recall": 1.0, "f1": 1.0
}
```

### Normalisation Unicode (résolution H2, H5)

`normalize_text` chaîne :
1. NFKC (unifie variantes de compatibilité).
2. NFKD + retrait des marques de combinaison (catégorie `M*`).
3. casefold (gère ß → ss, fold étendu).
4. Retrait des caractères de ponctuation/symboles (catégories `P*`,
   `S*`) — remplacés par un espace.
5. Collapse des espaces.

Couvre : « » ' œ ß diacritiques NFC/NFD, ponctuation française.

### Procédure d'annotation (P1.4.B)

Pour chaque épisode à annoter :
1. Récupérer le transcript et la durée totale.
2. Repérer chaque reco : titre + créateur + timestamp.
3. Distinguer `must_have: true` (reco énoncée sans ambiguïté) du
   nice-to-have (`false`).
4. Œuvres ambiguës (titre cité au pluriel, saga…) : une ligne par
   mention.
5. Sauvegarder en `tests/eval/golden_set/<source>-<guid>.json`.

Cible : 10 épisodes réels (P1.4.B — à ajouter à la roadmap).

## Conséquences

### Positives

- Tout changement de prompt/modèle est mesurable contre une baseline
  stable.
- F1 partageable dans les rapports + manifest JSON archivable.
- Harness agnostique du modèle : benchmark Haiku vs Sonnet vs règles.
- Architecture ouverte (Protocols + registries) : ajout d'un format,
  d'une source, ou d'un adaptateur sans toucher au harness.

### Négatives

- L'annotation manuelle est lente (≈ 15-30 min / épisode) et introduit
  un biais d'annotateur. Mitigation : 10 épisodes + relecture croisée.
- Le fuzzy match ne capture pas les **erreurs sémantiques fines**
  (« Drive » Refn vs « Drive » Mangold). Le créateur sert de
  désambiguïsation mais reste optionnel.
- Pas d'évaluation de la **qualité de l'enrichissement** (TMDB, Spotify) :
  hors scope.
- Hungarian O(n³) en pur Python — suffisant à l'échelle du golden set
  mais sous-optimal si on dépasse N=200 recos/épisode. Documenté.

### Notes

- Seuil fuzzy par défaut = 0.85 : empirique, à ré-évaluer après la
  première vraie campagne d'annotation.
- Tolérance timestamp globale par défaut = 5s (durcie depuis 30s) ;
  la tolérance per-reco (`timestamp_tolerance_sec` du golden set) reste
  prépondérante quand plus large.
- Item complémentaire **P1.4.B** : annoter 10 épisodes réels du dataset
  `un-bon-moment`.

## Historique des révisions

- 2026-06-10 (initiale) : décision principale, schéma d'annotation,
  classification, conséquences.
- 2026-06-10 (post-CR) : invariant comptable C1, Hungarian C2, strict
  guid C3, ExtractionSource/EvalReporter/RunManifest (P0 archi),
  EvalConfig, Unicode/ponctuation, registre REPORTERS, multi-source,
  per-episode, log JSONL, `compare` subcommand, CLI exit codes,
  CSV UTF-8 BOM, Markdown top/bottom 5.
