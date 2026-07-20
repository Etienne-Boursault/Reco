# ADR 0038 — Wizard CLI `reco init`

> **Renumérotation 2026-06-12** : initialement créé avec le numéro 0037 mais 0037 était déjà pris par `0037-docker-compose-deployment.md` (Dev #18 Phase 3). Renommé en 0038 par la coordination finale Phase 3.

- Statut : Acceptée
- Date : 2026-06-12
- Décideurs : équipe Reco

## Contexte

Roadmap Phase 3 — item #19. Le kit Reco est conçu pour être dupliqué
(cf. ADR 0028 fork boundary, `docs/fork-guide.md`). Aujourd'hui, un
forkeur·euse doit :

1. Copier `src/content/sources/un-bon-moment.json` à la main.
2. Renseigner ~10 champs (slug, title, rssUrl, hosts, theme.colors…)
   sans validation immédiate (la Zod du build remonte les erreurs en
   bout de chaîne, après `npm run build`).
3. Cloner / créer les répertoires `tools/output/` au premier run.

Cette friction d'onboarding est l'un des freins identifiés au moment
de la clôture Phase 2 (« kit duplicable mais pas zéro-friction »).

Options envisagées :

- **A. Wizard pur Node** (Inquirer/Prompts) — polyglot npm, nouvelle
  dépendance à maintenir, doublonne le pipeline Python existant.
- **B. Pas de wizard** — statu quo, friction documentée dans le
  fork-guide.
- **C. Wizard web Astro** — hors scope kit CLI-first, charge de
  maintenance UI déraisonnable pour la valeur.
- **D. Wizard Python + thin Node dispatcher** — réutilise le runtime
  Python déjà installé (pipeline tools/), `input()` natif, validation
  pré-écriture cohérente avec `tools/config/schema.py`. `bin/reco`
  Node sert uniquement à offrir `npx reco init` (pas de dépendance
  npm runtime).

## Décision

Adopter **l'option D** :

- `tools/reco_init.py` (CLI Python, argparse, `--ci` non-interactif).
- Package `tools/init/` : `slugify`, `validators`, `prompts`, `writer`.
- `bin/reco` (Node ESM) — thin dispatcher vers les modules Python
  (`tools.reco_init`, `tools.build_cache`, `tools.audit_yt_acast`, …).
- Préfère `tools/.venv/` s'il existe, sinon retombe sur `RECO_PYTHON`
  / `python3` / `python` selon plateforme.
- Génère `src/content/sources/<slug>.json` conforme au schéma Zod
  (`src/content.config.ts`) — slug regex stricte
  `^[a-z0-9]+(?:-[a-z0-9]+)*$`, theme.colors complet (bg / surface /
  text / muted / accent / accentText).
- Validation côté Python AVANT écriture (slug, URL, hex, prefix,
  email) ; Zod reste autorité au build.
- Atomic write (réutilise `tools.common.atomic_write_text`).
- Mode `--dry-run` pour CI/sanity ; `--force` pour ré-écrire ;
  `--output-dir` pour les tests (et forks dans monorepo).

i18n : wizard hardcodé FR pour Phase 3 — cohérent avec ADR 0025
(single-locale). Bascule envisagée si > 1000 forks ou demande
explicite d'une locale supplémentaire.

## Conséquences

- **Positives** :
  - Onboarding `npx reco init` → fichier source en < 1 minute.
  - Aucune dépendance npm runtime ajoutée (le `bin` Node est de
    quelques dizaines de lignes, sans `node_modules`).
  - Sortie déterministe (JSON trié, indent 2) — pas de diff parasite.
  - `--ci` rend le wizard scriptable (CI fork demo, tests E2E).
  - Validation immédiate des erreurs typiques (mauvais slug, URL HTTP
    manquante, hex invalide) — feedback localisé sans attendre Astro.

- **Négatives** :
  - Une commande Python supplémentaire à maintenir
    (`tools/reco_init.py` + `tools/init/`).
  - Wizard hardcodé FR — friction pour forkeurs non francophones,
    mitigée par `--ci` (skip-prompts).
  - `bin/reco` impose Python disponible côté forkeur (déjà requis
    par tout le pipeline `tools/`).

- **Notes / critères de bascule** :
  - Si > 1000 forks ou demande explicite : wizard web Astro
    (option C) ou i18n du wizard.
  - Le `bin/reco` peut accueillir d'autres sous-commandes
    (`reco audit`, `reco lint`, `reco enrich`, `reco embed`,
    `reco reports`) sans churn de l'API publique.
  - À revisiter quand `tools/.venv` deviendra géré par un installer
    standard (Hatch, uv) — actuellement détecté par convention.
