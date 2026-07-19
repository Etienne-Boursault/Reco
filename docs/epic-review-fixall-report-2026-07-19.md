# Rapport EPIC — Refonte /doutes, logos, revue exhaustive & fix-all (2026-07-19)

Session `26d8618a`. Méthode : TDD, SOLID, clean architecture, parallélisation multi-agents. Tout finding corrigé est accompagné d'au moins un test.

## 1. Résultat global

- **pytest** : suite complète **VERTE** (exit 0, ~3776 tests). Couverture `tools/` = **94 %** (voir §6 pour la lecture honnête).
- **vitest** : **654 tests verts** (58 fichiers). `RecoCard.astro` 98–100 %, `merchants.ts` **100 %**.
- **Test manuel** : review_server relancé **sans PYTHONPATH** (valide le fix imports) — `/`, `/doutes` (groupé par type), `/ep` → 200 ; `POST /route-inconnue` → **404** (plus de mutation silencieuse) ; site Astro épisode → 200 avec vrais logos de plateformes.

## 2. Stories livrées

| Story | Livré |
|-------|-------|
| **Refonte `/doutes`** | Regroupement **par type d'action** (À trancher / Signalements / Qui recommande / Faible confiance), puce épisode cliquable par item, sommaire à ancres, édition **inline** qui revient à `/doutes` (save **et** annuler). |
| **Logos de liens** | 19 SVG de plateformes créés sous `public/icons/platforms/`, `WHITELISTED_ICON_HOSTS` rempli — fin des trombones. |
| **Transcription (contexte antérieur)** | 12 épisodes transcrits (Mac mlx-turbo + llm réparé), extraits, 186 recos reliuées par 12 agents Opus. |

## 3. Revue 1 (relecture initiale) — corrigée

| # | Sévérité | Correctif | Test |
|---|----------|-----------|------|
| M1 | Majeur | Coercion `confidence` texte→float dans `_section_for` (crash `/doutes`) | ✅ |
| C1 | Critique | Bootstrap `sys.path` dans `common.py` — scripts lancés « comme documenté » (match_youtube standalone, `/add-reco`, extraction) | ✅ (5 tests d'invocation subprocess) |
| M2 | Majeur | `extract_all_batch` propage le vrai `transcriptSource`/`Model` par guid (fin de la corruption de timecodes YouTube) | ✅ |
| m1 | Mineur | Garde `https://` sur `customLinks`/`linkOverrides` (write) + `isSafeHref` (render Astro) | ✅ |
| m2 | Mineur | `/add-reco` : flash actionnable au lieu d'un 500 sur config absente | ✅ |
| m3 | Mineur | Fichiers-poubelle shell supprimés | — |

## 4. Revue 2 — EXHAUSTIVE (4 agents Opus, sans limite d'issues) — tout corrigé

### 4.1 Critique / High
- **CRITIQUE — XSS stocké** (`review_edit_form._render_overrides_section`) : le lien auto rendait des `externalIds` (website/deezer/…) en `href` sans valider le schéma → `javascript:` exécutable. **Fix** : `_safe_url` sur le href auto. ✅ test.
- **H1 — `transcribe.py --youtube` inversé** : le flag alimentait `prefer_acast` (positionnel) → forçait **Acast**. **Fix** : `--acast` explicite + passage en mot-clé. ✅ tests.

### 4.2 Medium (tous corrigés)
- **rev-render** M1 `_render_recap` crash durée-chaîne → `_safe_int` ; M2 « Annuler » de l'édition inline éjectait vers `/ep` → threading `edit_origin`.
- **rev-server** M1 route POST inconnue → `_save_status` (validate silencieux) → **routing explicite + 404** ; M2 body non-UTF-8 → `errors="replace"` ; M3 contrôle de port anti-CSRF jamais réellement testé → **faux `server` + tests port correct/incorrect**.
- **rev-pipeline** M1 `run_pipeline` extract sans verrou → `acquire_pipeline_lock` ; M2 `fetch_episodes` mojibake → `resp.content` ; **M3 dual-identity `common`/`tools.common`** (conséquence bénigne du bootstrap) → **documentée** (refactor 180 fichiers volontairement écarté) ; M4 perf `_persist_recos` O(ép×recos) → `_RunIndex` construit une fois ; M5 `match_youtube` faux matches (boost 0.90) → `_select_best_video` (départage par durée).
- **rev-astro** S1 `logoUrl` non validé (fuite tracking) → whitelist host + `isSafeHref` (write + render).

### 4.3 Low / Nit (tous corrigés)
- **rev-server** : code mort `_send_error`/`_csrf_check` retirés ; guid `GET /ep` validé ; toast synthétisé sur `/save` JSON ; action `/save` inconnue rejetée (whitelist) ; `_action_merge` 500-safe ; test qui prenait le vrai verrou → mocké.
- **rev-render** : flash `/doutes` sans JS (bannière) ; `_send_json_post` dérive `edit_origin` du referer ; code mort (`_SECTION_ORDER`, branche `section_key`, imports inutilisés) ; `next(..., None)` dans `render_merge_preview` ; convergence garde URL (`_is_https_url` insensible casse + `_safe_url` au rendu + garde `externalIds` au write).
- **rev-astro** : validateur unique `isSafeUrl` ; handle Instagram encodé/validé ; `reco.links`/`customLinks` filtrés par `AVOID_DOMAINS` (`isAvoidedUrl` anti-faux-positif) — **politique éthique Amazon/Bolloré enfin appliquée** ; props mortes retirées ; a11y emojis (role/aria-label conteneur + aria-hidden enfants).
- **rev-pipeline** : batch `main()` try/except ; `season/number` manuels non écrasés ; `_parse_date` robuste ; défaut `--extract-model` aligné sur `extract_recos.MODEL` ; regex index ancrée.

## 5. Tests & couverture ajoutés
- **Nouveaux fichiers** : `tests/test_script_invocation.py` (invocation standalone C1), `tests/merchants/test_resolve_links.test.ts` (41 tests, merchants 100 %).
- **Étendus** : test_review_server (+~), test_review_doubts, test_review_edit, test_extract_recos, test_match_youtube, test_fetch_episodes, test_run_pipeline, test_common, test_transcribe, tests/components/test_reco_card.
- **Couverture par cluster** : pipeline ~99 %, review_server 97 %, merchants 100 %, RecoCard 98–100 %. **100 % sur tout le code ajouté/modifié.**

## 6. Lecture honnête de la barre « ≥95 % partout / 100 % nouveaux »
- **100 % sur les nouveaux fichiers** : tenu (merchants.ts 100 %, code ajouté 100 %).
- **≥95 % projet-wide** : **non atteint littéralement**, mais **pas à cause de l'EPIC** :
  - `tools/` 94 % — tiré sous 95 % par ~6 **scripts one-off jetables à 0 %** (`compare_4_llms`, `compare_extract`, `migrate_guests_parsed`, `rerun_*`, `retry_gpt4o`), jamais testés, hors périmètre. Les fichiers EPIC sont à 93–99 % (résidus = `except` défensifs / `__main__`).
  - JS branches 84,9 % — tiré par des modules SEO/OG legacy (`jsonld` 65 %, `meta-loader` 60 %) hors EPIC.
  - **Option** : exclure les scripts jetables de la mesure (coverage `omit`) ferait passer `tools/` au-dessus de 95 % — décision à valider (non fait sans ton accord, pour ne pas « maquiller » la métrique).

## 7. En suspens (décisions / hors-scope)
- **Recherche de liens réels (Task 5)** : bloquée — WebSearch épuisé pour la session (`CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` à relever + relancer Claude Code).
- **16 recos supprimées** (`0518.json`…) repérées en `D` git — récupérables via `git checkout` (préexistant, à trancher).
- **Doc** (audit) : `DATA_SCHEMA.md` et `tools/README.md` périmés, pas de doc `agentReview`/`/doutes`/transcription distribuée ; `docs/` non commité (historique arrêté au 3 juin).
- Rien n'est commité (aucun commit sans ta demande).
