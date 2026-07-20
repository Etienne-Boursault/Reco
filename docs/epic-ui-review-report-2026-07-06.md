# EPIC « UI review » — Rapport 2026-07-06

Déclencheur : retours utilisateur du 2026-07-05 après contrôle des vagues
d'agents de review (bug rename invité, distinction visuelle des citations,
titres YouTube anglais, demande de séparation des auto-promos d'invités).

Process appliqué (mandat) : par story — dev TDD → code-review sans limite
d'issues → correction de TOUTES les issues ; puis CR cumulative exhaustive
sur l'EPIC entière (2 reviewers, backend + frontend) → correction de toutes ;
test manuel ; ce rapport.

## Stories livrées

| # | Story | Contenu | CR | Issues corrigées |
|---|---|---|---|---|
| 1 | Bug rename invité `guestsParsed` | Le rename ne touchait que `ep.guests` → le panneau réaffichait l'ancien nom. Fix : exclusion de l'ancien nom + promotion du nouveau dans `guests` (helpers `_exclude_add`/`_exclude_remove`/`_reconcile_parsed_rename`). | GO | 12 (3 MED, 5 LOW, 4 NIT) |
| 2 | Citations validées en bleu | `.row.done.citation` (fond `#101a24`, liseré `#4a8edb`) — vert=reco, bleu=citation, ambre=œuvre d'invité, rouge=écarté, y compris états croisés `discarded.*`. | GO | 9 (1 MED, 3 LOW, 5 NIT, avec Story 3) |
| 3 | Titres RSS prioritaires | Le titre RSS français prime sur le `youtubeTitle` (formats anglais « A Good Time with… », ép. 40/48/50/S5E25…) ; titre YT en tooltip quand il diffère, y compris sans lien et sur /doutes. | GO | (groupées avec Story 2) |
| 4 | Marqueur « œuvre d'invité » (`guestWork`) | Flag booléen (pas de nouveau `kind`), bouton ⭐ « Œuvre d'invité·e » dans le review server, verdict `guest-work` pour les agents, badge + section dédiée sur la page épisode du site public. Décision produit : **incluses dans tous les chiffres**, seule la page épisode les présente à part. | GO conditionnel | 10 + gaps tests (1 HIGH décision produit, 2 MED, 2 LOW, 5 NIT) |

## CR cumulative EPIC (2 reviewers parallèles)

**Backend (12 issues + 1 transverse)** — dont : pré-coche des checkboxes
« Reco de » par sous-chaîne (attribution silencieusement fausse, classe
d'erreur documentée en mémoire projet) ; lecteur YouTube absent de /doutes ;
éjection vers /ep après action depuis /doutes (promesse « un seul passage »
non tenue) ; 4 fichiers > 500 lignes ; 0 test sur le JS client.

**Frontend (16 issues)** — dont : contraste AA du badge ambre cassé sur les
forks à thème clair (2.19:1 → corrigé à 6.70:1 via `--guestwork` dérivé du
thème par `color-mix`) ; `<h1>` dans le landmark `<nav>` (WCAG 1.3.1) ;
libellés hors i18n ; collision d'emoji 🎤 avec le type « artiste » (→ ⭐) ;
compteurs incohérents entre annuaire/épisode/OG (réconciliés : « X
recommandations · dont Y œuvres d'invité·es ») ; « Recommandée N fois »
comptait les citations.

**Toutes les issues (~60 sur l'EPIC) corrigées**, aucune CRITICAL détectée
sur l'ensemble.

## Dette structurelle réglée (M4/M5)

Découpes avec réexports lazy (PEP 562) — rétro-compat totale des tests et
consommateurs :
- `review_render.py` 658 → **393** + `review_render_page.py` 318 (pages)
- `review_edit.py` 635 → **289** + `review_edit_form.py` 385 (rendu du form)
- `review_routes.py` 765 → **380** + `review_routes_merge.py` 281 + `review_routes_reco.py` 220
- `review_client.js` 1198 → **254** (core) + `review_client_cluster.js` 304 + `review_client_keyboard.js` 488 + `review_client_toolbar.js` 220 — namespace `window.__reco`, concaténation ordonnée dans `_CLIENT_JS`
- **Tous les fichiers `tools/review_*` ≤ 500 lignes** (règle CLAUDE.md tenue)
- Premier harnais de tests du JS client : `tests/js/` (happy-dom, hooks de
  test exposés uniquement sous `window.__recoTestHooks`) — 18 tests
  (tri/statuts/recherche/URL, clé `guestwork` incluse)

## Corrections de données liées (retours utilisateur)

14 corrections appliquées sur E2/E7/E9/E20 (Gisèle Kérozène/Jan Kounen,
fusion Laborit ×3, Brazil et Le sens de la vie → citation, timecodes Hôtel du
Nord/Panique recalés sur transcript, Bref 2 → discard, fusion Ego + l'usine à
trombone, Devil's Plan : timecode recalé — l'œuvre est bien dans le
transcript, translittérée —, Jardin d'hiver → Henri Salvador, Guillermo Guiz
→ citation, Sus + Instagram officiel, aphorismes d'Haroun → discard,
Mona Guba ×3 → discard). Politique éditoriale enrichie de 10 règles en
mémoire projet pour les futures vagues d'agents.

## Chiffres finaux

| Suite | Résultat |
|---|---|
| pytest (suites review) | **462 verts** |
| vitest (global) | **593 verts** (dont 18 JS client, 34 front EPIC) |
| Build Astro | **5 587 pages**, zéro erreur |
| Coverage front | lines 94 % / funcs 91 % / stmts 91 % (gate 80) |
| `review_guests.py` | 100 % |

## Test manuel (smoke, serveur redémarré)

- Index : toolbar, lien « 🤖 Doutes agent », 4 IIFE JS chargées ✓
- /doutes : lecteur YouTube inline, blocs agent en `<li>` valides, bouton
  « Œuvre d'invité·e », retour sur /doutes après action ✓
- Épisode S5E2 : bouton ⭐, toolbar tri/repli, badge 🤖, citations bleues ✓

## Points d'attention

- La feature `guestWork` est **dormante** côté site public (aucune reco
  marquée à ce jour) — elle s'activera avec les prochaines vagues d'agents
  (verdict `guest-work` disponible dans `apply_verdicts.py`) et le bouton ⭐.
- `apply_verdicts.py` (scratchpad) est un miroir MANUEL de
  `_apply_save_action` — avertissement de parité documenté en tête des deux.
- Ne jamais émettre `guestWork: null` côté writer recos (schéma strict,
  commentaire dans `content.config.ts`).
