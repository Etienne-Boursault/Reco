# ADR 0023 — Re-enrich proactif TMDB/Music avec `enrichedAt` par champ

- **Statut** : Accepté (Phase 2 Vague 1, item roadmap #17, juin 2026)
- **Décideurs** : Etienne (lead), agent backend-dev P2.17
- **Tags** : enrichment, freshness, cache, idempotence, datasets-vivants

## Contexte

Les recos film/série sont enrichies par `tools/enrich_tmdb.py` (watch providers
FR + JustWatch + TMDB id). Les recos musique le sont par `tools/enrich_music.py`
(Deezer/Spotify deeplinks). Ces deux scripts sont aujourd'hui des passes
**one-shot** :
- Une reco est enrichie au moment où on l'extrait,
- puis **plus jamais**, sauf à supprimer manuellement l'`externalIds` et
  relancer la passe complète.

Or les datasets TMDB et MusicBrainz vivent : `release_date` corrigé, `runtime`
ajusté, nouveau provider ajouté (par exemple Apple TV+ qui récupère un titre
Netflix), liens JustWatch qui changent quand une plateforme perd les droits.
Sans refresh, le site exposera lentement des données stale ou cassées.

Alternatives envisagées :
1. **Re-passe complète périodique** (cron mensuel `enrich_tmdb --force --source all`).
   Rejeté : gaspille quota API (~10 000 recos × N champs), écrase les overrides
   manuels (`linkOverrides`), pas granulaire.
2. **Webhooks TMDB**. Rejeté : TMDB ne propose pas de webhooks à ce jour
   (juin 2026). MusicBrainz non plus.
3. **Pas de refresh — la donnée se dégrade**. Inacceptable pour un kit
   self-hostable à durée de vie longue.

## Décision

Adopter un modèle d'enrichissement **incrémental, champ par champ**, fondé sur
trois pièces :

### 1. Flag `enrichedAt` par champ (schéma)

Chaque reco (et chaque Item dans la couche v2) peut porter un sous-objet
optionnel :

```json
"enrichedAt": {
  "externalIds.tmdb": "2026-04-15T10:00:00Z",
  "externalIds.justwatch": "2026-04-15T10:00:00Z",
  "watchProviders": "2026-04-15T10:00:00Z"
}
```

- Clés = noms de champs (chemin pointé pour les champs imbriqués).
- Valeurs = timestamps ISO8601 UTC (`...Z`) — instant du dernier enrichissement.
- **Champ absent ⇒ jamais enrichi** (équivalent à infiniment stale).

Forward-compat strict : pas de bump `schemaVersion`. Les recos pré-existantes
restent valides. Étendu côté Zod via `z.record(z.string(), z.string()).optional()`
sur les collections `recos` et `items`.

### 2. CLI `tools/refresh_enrichment.py`

Outil dédié, séparé des scripts d'enrichissement initiaux, qui :
- Itère sur les recos d'une source (ou `all`).
- Pour chaque champ candidat du provider applicable (TMDB pour film/série,
  Music pour musique/album/artiste), détermine s'il est stale via
  `now - enrichedAt[field] > older_than`.
- Refresh **uniquement** les champs stale via le provider correspondant.
- Met à jour `enrichedAt[field]` avec le nouveau timestamp.
- Écrit le fichier de manière atomique (`atomic_write_text`) seulement si
  le contenu change réellement.

Flags : `--source <id>|all`, `--field <name>`, `--provider <tmdb|musicbrainz|all>`,
`--refresh-older-than <duration>` (défaut `90d`, format `30d/12w/6m/2y/48h`),
`--dry-run` (défaut) / `--apply`, `--limit N`, `--ignore-server-lock`.

Lockfile pipeline (cf. ADR 0011 `review_lock.py`).

### 3. Cache HTTP SQLite (`requests-cache`)

Backend : `tools/output/http_cache.sqlite` (déjà gitignored via `tools/output/`).
TTL configurable par URL :
- TMDB : 24 h (watch providers évoluent, ids stables).
- MusicBrainz : 7 j (très stable).
- Deezer : 24 h.

Le wrapper `enrichment.http_cache.CachedSession` ajoute des compteurs
hit/miss/requests pour métriques CLI.

### 4. Refresh sous-champ uniquement

Le module `enrichment.field_refresher.partial_update(item, field, new_value)`
**préserve** les champs non touchés (overrides manuels, `customLinks`,
`linkOverrides`). Aucun risque d'écraser un override quand on rafraîchit
`runtime` seul.

## Conséquences

**Positives**
- Économise quota API (cache + ciblage par champ stale).
- Granulaire : on peut ne re-tester QUE `watchProviders` mensuellement.
- Audit trail naturel via `enrichedAt` (quand le champ a-t-il été vérifié ?).
- Overrides manuels préservés.
- 100% rétro-compatible (champ optionnel).

**Négatives**
- Complexité schéma : un sous-objet de plus.
- Lecture des recos doit tolérer son absence (déjà testé).
- Gestion clés API obligatoire pour `--apply`.

## Critères de bascule (futur)

- Si TMDB ajoute un endpoint webhooks ou un endpoint `since=<timestamp>` →
  simplifier en remplaçant le scan systématique par un pull différentiel.
- Si on observe une dérive forte de la qualité (`enrichmentSuspect` qui
  explose après un refresh massif), introduire une étape de validation
  humaine avant d'appliquer.

## Pass A — Bugs production corrigés (2026-06-11)

Cinq CRITICAL bugs identifiés en audit, corrigés en TDD strict (scope étroit,
pas de refacto Provider Protocol). Pass B/C/D/E (Provider Protocol formel,
extraction `cli_runner`, `Settings`, ADR dédié provider) restent à dispatcher.

- **C3 — `TmdbProvider` sans `api_key`** : `_candidate_fields_for` instanciait
  `TmdbProvider()` paresseusement à chaque reco, écrasant l'instance build
  par `run()` avec credentials → 100% des appels TMDB échouaient 401 en prod.
  Fix : `run()` construit la liste de providers UNE FOIS avec credentials,
  passe `providers: Sequence[Provider]` à `plan_refresh` /
  `_candidate_fields_for`. `provider_factory` reste injectable pour tests.
- **C4 — `MusicProvider` sans `spotify_token`** : `spotify_token=None` cablé
  en dur → Spotify jamais rafraîchi en prod ET faux audit trail
  (`enrichedAt[externalIds.spotify]` mis à jour sans appel réel). Fix :
  `main()` charge `SPOTIFY_CLIENT_ID/SECRET` depuis env, `run()` dérive le
  token via `enrich_music.spotify_token(...)` UNE FOIS en amont via
  `_resolve_spotify_token(...)`, puis le passe au `MusicProvider`. Si pas
  de creds : log warning, `MusicProvider.refresh` skip honnêtement le champ
  `spotify` (pas de trace audit) tout en laissant Deezer fonctionner.
- **C5 — Logique "inchangé" cassée** : `if ext.get("tmdb") != before_ext.get("tmdb") or "tmdb" in ext`
  était toujours True dès qu'un résultat TMDB tombait → marqueur inactif,
  trace bruyante. Fix : politique uniforme sur les 3 branches TMDB
  (`externalIds.tmdb`, `externalIds.justwatch`, `watchProviders`) : si
  l'appel réussit, on trace systématiquement `enrichedAt[field]` (audit
  "vérifié à T"), avec idempotence H6 sur `externalIds.tmdb` (noop si
  valeur ET timestamp identiques).
- **C6 — Pas de convention `not_found` côté Music** : asymétrie silencieuse
  avec TMDB. Fix : `MusicProvider.refresh` pop `_enrich_status` et retourne
  `(0, "not_found")` quand `enrich_music` le signale ; ajout des compteurs
  séparés `RefreshStats.not_found_tmdb` / `not_found_music` (audit ciblé)
  en plus du compteur global existant `not_found`.
- **P0-5 — `enrichedAt` corrompu écrasé silencieusement** : si
  `item["enrichedAt"]` n'était pas un dict (cas pathologique : string
  accidentelle), `partial_update` / `update_nested` l'écrasaient
  silencieusement par `{}` → perte irrécupérable de l'audit trail. Fix :
  classe `EnrichedAtCorruptedError(ValueError)` définie dans
  `enrichment.field_refresher` et re-exportée par `enrichment.__init__`
  + `refresh_enrichment` ; check explicite en début de `partial_update` /
  `update_nested` ; `_ensure_enrichedat_dict` en amont du pipeline `run()`
  catch et incrémente `RefreshStats.corrupted_skipped`. Tests dédiés :
  `test_partial_update_raises_on_corrupted_enrichedAt`,
  `test_update_nested_raises_on_corrupted_enrichedAt`,
  `test_P0_5_corrupted_item_skipped_during_run`.

**Validation** : 2872 tests verts (baseline 2871 + 1 nouveau test ;
`test_corrupt_enrichedat_replaced_with_dict` retourné en
`test_partial_update_raises_on_corrupted_enrichedAt` car la sémantique a
été inversée par P0-5). Zéro régression hors scope.

## Pass B — Settings injectables (P3.5-B, 2026-06-12)

Dette Phase 2.5 reportée par Pass A : les seuils étaient hardcodés dans
``argparse``, ce qui viole l'ADR 0001 (SSOT — config par source dans
``SourceConfig.extra``). Aligne ``refresh_enrichment`` sur le pattern
``enrich_audit``/``match_audit``/``lint`` livré Sprint 2.

- **Nouveau** : ``tools/enrichment/settings.py`` —
  ``RefreshEnrichmentSettings`` (frozen, slots) avec
  ``from_source_extra(extra, overrides=...)`` déléguant à
  ``audit_core.settings.from_source_extra`` (SSOT, ADR 0019).
- **Champs** : ``older_than`` (timedelta, coerce depuis "30d"),
  ``provider_filter`` (all/tmdb/music/musicbrainz), ``ttl_per_provider``
  (MappingProxyType — forward-compat, pas encore lu par ``run()``),
  ``prioritize_suspect`` (forward-compat — priorisation items
  ``enrichmentSuspect``).
- **CLI inchangée** : ``--refresh-older-than``, ``--provider`` restent
  des overrides au-dessus des défauts ``Settings``.
- **Tests** : ``tests/enrichment/test_settings.py`` (18 tests TDD).

Reporté Pass B+ : extraction d'un ``enrichment.cli_runner`` complet
(``RunOptions``/``run_refresh`` pure logic). Le couplage actuel
``main()`` → ``run()`` est déjà raisonnablement testable ; l'extraction
n'apporterait pas de gain immédiat sans risquer une régression sur les
Providers credentialed (TmdbProvider/MusicProvider).

## Liens

- Roadmap Phase 2 item #17.
- Code : `tools/refresh_enrichment.py`, `tools/enrichment/*`.
- Tests : `tests/test_refresh_enrichment.py`, `tests/enrichment/test_*.py`.
- Schéma : `src/content.config.ts` (collections `recos` et `items`).
- ADR liés : 0011 (review_lock), 0014 (audit_tmdb / enrichmentSuspect).
