# ADR 0013 — Audit a posteriori des matchs YouTube ↔ Acast

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

`tools/match_youtube.py` associe chaque épisode RSS Acast à la vidéo
YouTube de la chaîne en maximisant la similarité de titre normalisée.
La méthode marche dans 90 % des cas mais a deux failles documentées
(cf. mémoires `reco-cleanup-collisions`, `reco-yt-format-titles`) :

1. **Titres de format** : la chaîne `@KyanKhojandi` publie sous des
   titres très différents du titre RSS basique (« A Good Time with
   X », « THE JOHNNY DEPP GAME WITH X », « Guess the punchline with
   X »…). La similarité chute sous le seuil et le matcher peut
   verrouiller la mauvaise vidéo (typiquement un multiblindtest avec
   le même invité).
2. **Collisions silencieuses** : une même vidéo YouTube se retrouve
   parfois attribuée à deux épisodes RSS différents. Côté pipeline,
   le transcript et les recos qui en découlent correspondent au
   contenu de l'autre vidéo — pollution toxique des données.

Le problème : aujourd'hui ces erreurs ne sont visibles qu'à l'œil nu,
en relisant les recos ou en re-OCRisant les miniatures. Pas de
garde-fou automatique.

## Options examinées

1. **Fixer le matcher à la source** (refondre `match_youtube.py`).
   Coûteux et risqué : le matcher est largement utilisé et la
   stratégie « titre + suffix patterns » couvre 90 % des cas. Tout
   refondre pour traiter les 10 % restants explose le scope.
2. **Audit a posteriori avec heuristiques indépendantes**
   (choix retenu). On laisse le matcher inchangé et on ajoute un
   _checker_ séparé qui regarde chaque épisode après matching et
   flag les anomalies via un champ `matchSuspect: true`.
3. **Embedding sémantique du transcript** (sentence-transformers).
   Plus puissant mais introduit une dépendance lourde (modèle ~500 Mo,
   GPU recommandé) et complexifie le pipeline pour un gain marginal
   sur le périmètre actuel.

## Décision

Option 2 : nouveau package `tools/match_audit/` + CLI
`tools/audit_yt_acast.py`. Architecture SOLID :

- **SRP** : un module par check (durée, intro, titre).
- **OCP** : `MatchAuditService(checks=[...])` — ajouter un check =
  nouveau fichier + entrée dans la liste, pas de modification de la
  classe.
- **DIP** : les checks reçoivent leurs accesseurs (`*_transcript_provider`)
  par injection — testables sans I/O.

### Checks implémentés

| Check | Sévérité | Seuil | Rationale |
|---|---|---|---|
| `duration_check` | error | écart > 5 % | Signal le plus fiable : un audio de 1h vs vidéo de 1h30 ≠ même contenu. 5 % couvre les jingles d'intro/outro qui diffèrent légèrement entre Acast et YouTube. |
| `intro_embedding_check` | error | similarité texte < 0.4 | Compare les 500 premiers caractères des transcripts Acast vs YouTube (proxy des ~30 premières secondes). 0.4 = seuil empirique laissant passer les variations Whisper sans rater une vidéo complètement différente. |
| `title_similarity` | **warning** | similarité < 0.3 | Re-mesure de la similarité titre RSS↔YT. Bas-fiabilité (les titres de format `@KyanKhojandi` font chuter le score alors que le match est correct) — d'où le statut **warning** : visible dans le rapport mais ne déclenche pas `matchSuspect`. |

Un épisode est marqué `matchSuspect: true` SSI au moins un check de
sévérité `error` a flaggué. Les warnings n'enclenchent rien — ils
servent à l'humain qui investigue à la main.

### Embedding sémantique reporté

L'embedding sémantique (sentence-transformers / OpenAI embeddings) est
**reporté en Phase 2** :
- Le check texte couvre déjà 80 % des cas (les vraies collisions
  produisent des transcripts radicalement différents — un humain
  même non technique le voit).
- L'ajout d'une dépendance lourde pour gagner 10-15 % de rappel n'est
  pas justifié à ce stade.
- Si Phase 2 le requiert, l'architecture le permet : nouveau module
  `embedding_check.py` injecté dans la liste `checks=[]`.

### Schema

Extension du schéma Astro `episode` : `matchSuspect: z.boolean().optional()`.
Champ optionnel → backward-compatible avec les 2866 épisodes existants.

### CLI

```
python tools/audit_yt_acast.py --source <id> --dry-run     # liste, ne modifie pas
python tools/audit_yt_acast.py --source <id> --apply       # flag matchSuspect
python tools/audit_yt_acast.py --source <id> --report json # sortie machine
python tools/audit_yt_acast.py --source <id> --report markdown  # sortie humaine
```

Acquiert le `pipeline_lock` (cohérent avec les autres scripts du
pipeline).

## Conséquences

### Positives

- Détection automatique des mauvais matchs sans toucher au matcher.
- Le flag `matchSuspect` est visible côté review_server (à brancher
  ultérieurement) pour orienter l'effort humain.
- Idempotent : `--apply` peut tourner à chaque pipeline sans saturer
  le diff Git si rien n'a changé.

### Négatives / Risques

- **Faux positifs** : 5 % de tolérance sur la durée est strict ; des
  épisodes avec long pré-générique YT peuvent être flaggés à tort.
  Mitigation : on ne supprime rien, on flag — l'humain tranche.
- **Faux négatifs** : si une vidéo YT mal-matchée a par hasard la même
  durée ET un intro générique standard, l'audit ne la verra pas.
  Mitigation : check titre en warning reste visible.
- **Couplage transcript** : `intro_check` ne fonctionne que si les
  deux transcripts (Acast ET YouTube) sont présents. Aujourd'hui peu
  d'épisodes ont les deux ; le check est silencieusement no-op dans
  ce cas (retourne None).

## Validation

- 45 tests initiaux, 100 % couverture (`tools.match_audit` + `tools.audit_yt_acast`).
- Démo réelle sur `un-bon-moment` (104 épisodes) : 1 épisode suspect
  (`6599c3998e40b300163f8618`, écart durée 7 %), 2 warnings de titre
  cohérents avec les titres de format documentés.
- `npm run build` : OK (schéma Zod accepté).

## Suivi (CR senior + CR archi — 2026-06-10)

Itération de durcissement appliquée. Points-clés :

- ADR **0015** créé pour formaliser le pattern sidecar (en miroir d'ADR
  0014 côté `enrich_audit`).
- Convention de nommage des transcripts fixée :
  `tools/output/transcripts/<source>/<slugify(guid)>.{acast,youtube}.txt`.
  Plus aucun fallback `.txt` partagé (ambigu — risquait un faux
  "intro identique" entre Acast et YT).
- Seuils injectables CLI (`--duration-tolerance`, `--intro-threshold`,
  `--intro-chars`, `--title-threshold`) ET via `SourceConfig.extra[
  "match_audit"]` (forward-compat — extension officielle de
  `SourceConfig` reportée à la convergence Phase 1).
- Renommage `intro_embedding_check.py` → `intro_text_similarity.py`
  (ancien nom conservé comme alias rétrocompat — réservé pour
  l'implémentation embedding Phase 2).
- Mode CLI clarifié (modes mutuellement exclusifs `--check`/`--apply`/
  `--undo-last` séparés du format `--format`).
- `--apply` est désormais réversible via `--undo-last` (relit le dernier
  `_run_<ts>.jsonl` posé dans le dossier sidecar).
