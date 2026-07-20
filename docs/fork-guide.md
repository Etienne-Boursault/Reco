# Fork guide — adapter Reco à votre podcast

Ce kit est conçu pour être dupliqué. Cette page liste les points
d'adaptation et les filets de sécurité à exécuter avant de déployer.

## 0. Démarrage rapide — wizard `reco init` (recommandé)

Depuis P3.19 (ADR 0038), un wizard CLI génère `src/content/sources/<slug>.json`
en posant quelques questions :

```bash
# Mode interactif (FR)
npx reco init
# ou (équivalent)
node bin/reco init
# ou (Python direct)
python -m tools.reco_init

# Mode non-interactif (CI, scripts) — flags requis : --slug, --name, --rss-url
python -m tools.reco_init --ci \
  --slug=mon-podcast --name="Mon Podcast" \
  --rss-url=https://example.com/rss.xml \
  --hosts="Alice,Bob" --accent=#ffd23f
```

Flags utiles : `--dry-run` (affiche le JSON sans écrire), `--force`
(écrase un fichier existant), `--output-dir <path>` (autre que
`src/content/sources`).

Le wizard valide slug / URL / hex / prefix AVANT écriture et écrit
atomiquement. Les champs optionnels du schéma (tagline, description,
youtubeChannel, avoidBrands, extractionAnchorPatterns, etc.) sont à
compléter manuellement après coup — voir §1 ci-dessous.

## 1. Identité de la source (manuel ou complément du wizard)

1. Créer `src/content/sources/<mon-slug>.json` en copiant
   `un-bon-moment.json` comme base — OU laisser `reco init` (§0) le
   générer puis compléter.
2. Renseigner : `id`, `title`, `tagline`, `hosts`, `description`,
   `rssUrl`, `youtubeChannel`, `recoPrefix`.

## 2. Couleurs (theme.colors)

Le bloc `theme.colors` pilote toute l'identité visuelle (variables CSS
injectées par `<Layout>`). Modifier les 6 valeurs hex :

```json
"theme": {
  "colors": {
    "bg":         "#0e0e10",
    "surface":    "#17171c",
    "text":       "#f6f4ee",
    "muted":      "#9a99a3",
    "accent":     "#ffd23f",
    "accentText": "#0e0e10"
  }
}
```

⚠️ **Obligatoire** : faire tourner le check de contraste après modification.

```bash
npm run test:contrast
```

La commande boucle sur toutes les sources de `src/content/sources/*.json`
et valide WCAG AA pour chacune (cf. ADR 0030). Tant que ça ne passe pas
au vert, le déploiement est bloqué.

## 3. Locale & i18n (optionnel)

Si votre podcast est en anglais (ou autre) :

1. Copier `src/i18n/fr.ts` en `src/i18n/<lang>.ts` (ex. `en.ts`).
2. Traduire les valeurs.
3. Enregistrer la locale dans `src/i18n/index.ts` (ajouter à l'objet
   `locales`).
4. Passer `lang="en"` au `<Layout>` (ou ajouter un champ optionnel
   `lang` à la source et le lire dans les pages).

Cf. ADR 0025.

## 4. Validation a11y avant déploiement

### Commandes obligatoires

```bash
# Build statique
npm run build

# Scan HTML (skip-link, alt, headings, ARIA, etc.)
npm run test:a11y

# Contraste WCAG AA (palette par défaut + chaque source)
npm run test:contrast

# Tout en un :
npm run test:a11y:all
```

Ces trois commandes tournent aussi en CI (`.github/workflows/a11y.yml`),
mais elles doivent être vertes en local AVANT de pousser un fork.

### Checklist Lighthouse (manuelle, recommandée par release majeure)

Sur ces 3 pages, viser **score a11y ≥ 95** :

- [ ] `/` (homepage des podcasts)
- [ ] `/<slug>/` (catalogue d'une source)
- [ ] `/<slug>/episode/<guid>/` (page épisode)

Si le score descend < 90, ne pas merger (cf. ADR 0022).

### Audit dynamique (optionnel mais conseillé)

```bash
# Sert le build local
npx http-server dist -p 4321 &
# Lance pa11y-ci
npx pa11y-ci \
  http://localhost:4321/ \
  http://localhost:4321/<slug>/ \
  http://localhost:4321/<slug>/episode/<guid>/
```

## 5. Note réglementaire EAA (2025+)

La **European Accessibility Act** s'applique depuis juin 2025 à tous les
sites B2C accessibles en Europe — y compris un kit duplicable comme
celui-ci. WCAG 2.1 AA est le minimum légal. Le projet vise WCAG 2.1 AA
+ critère 2.5.8 de WCAG 2.2 (tactile ≥ 24×24 CSS px).

Cf. ADR 0022 pour le détail des critères couverts.

## 6. Liens utiles

- ADR 0022 — Accessibilité WCAG AA
- ADR 0030 — Design tokens & theming multi-source
- ADR 0024 — CI quality gates
- ADR 0025 — Stratégie i18n
- `tests/a11y/check_a11y.mjs` — règles statiques
- `tests/a11y/check_contrast.mjs` — règles contraste
- `src/styles/tokens.ts` — palette SSOT
- `src/i18n/fr.ts` — strings UI

## 7. FAQ rapide

**Q : J'ajoute une 4e couleur dans `theme.colors`. Que faire ?**
A : Étendre `ThemeColors` dans `src/styles/tokens.ts` et le schema Zod
dans `src/content.config.ts`. Ajouter les cas de contraste pertinents
dans `contrastCases`.

**Q : Mon nouveau accent est sombre, le focus ring est invisible.**
A : Le halo `box-shadow` du focus est dimensionné pour rester ≥ 3:1 sur
n'importe quel fond grâce à `color-mix(in oklab, var(--bg) 80%, transparent)`.
Si la palette inverse l'usage (bg clair, accent sombre), inverser le mix.
Vérifier avec `npm run test:contrast` qui couvre ce cas.

**Q : J'ai un texte qui contient des mots étrangers.**
A : Wrapper-les dans `<span lang="en">…</span>` à la main. La détection
automatique n'est pas en place (ADR 0022, limite assumée).

## 8. Variables d'environnement

### Obligatoires en production

- `SITE_URL` (ex. `https://mon-podcast.fr`) — base URL du déploiement.
  Fail-fast si absent en prod (P2.13).

### Requises pour les signalements visiteurs (P2.16, ADR 0034)

- `REPORTS_SECRET` (≥ 16 caractères aléatoires) — HMAC pour signer les
  captcha tokens.
- `REPORTS_REQUIRE_SECRET=1` — force la levée d'exception si
  `REPORTS_SECRET` absent (mode strict opt-in).
- `REPORTS_IP_SALT` (≥ 16 chars) — salt pour hash IP rate-limit.
- `TRUSTED_PROXIES` (CSV d'IPs reverse proxy) — autorise la lecture de
  `x-forwarded-for` côté handler.

### Requises pour les enrichissements (P2.17, P1.7, P1.8)

- `TMDB_API_KEY` — clé v3 TMDB pour films/séries.
- `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` — pour Spotify
  (P2.17 C4).
- `RECO_QUIET=1` — réduit la verbosité des CLIs (optionnel).

## 9. Modules Phase 2

### Signalements visiteurs (P2.16, ADR 0034)

- Endpoint `/api/report` est statique par défaut : sans adapter SSR,
  le POST renvoie 405.
- Pour activer le POST en prod : installer `@astrojs/node` (ou Vercel /
  Netlify adapter), basculer `output: 'hybrid'` dans `astro.config.mjs`.
  Le marqueur `export const prerender = false;` est déjà présent dans
  `src/pages/api/report.ts` (P0-2 final Phase 2) — Astro 5 émet un
  warning au build static mais ne casse pas.
- Sans adapter : le `ReportForm` détecte le 405 (ou network error) et
  révèle un bouton "Envoyer par email" qui construit un `mailto:`
  pré-rempli vers `siteConfig.contactEmail` (à configurer dans
  `src/config/site.ts`). Un fallback `<noscript>` est aussi exposé.

### Recherche client-side (P2.9, ADR 0035)

- `dist/search.json` (~471 KB pour une source de 2651 items) est
  régénéré à chaque `npm run build`.
- MiniSearch BM25 côté client, palette `Cmd+K` / `Ctrl+K` / `/` montée
  globalement par `<SearchPalette />` dans `Layout.astro` (P0-1).
- Critère de bascule : si `search.json` dépasse 5 MB, splitter par
  source ou basculer sur Algolia DocSearch.

### Galeries (P2.10, ADR 0031)

- Routes auto-générées : `/[source]/films`, `/livres`, `/musique`,
  `/series`, `/invite/[name]`.
- ItemList JSON-LD émis. A11y WCAG AA validée.

### Page œuvre canonique (P2.11, ADR 0032)

- Routes `/[source]/oeuvre/[itemId]` (2622 par source `un-bon-moment`).
- Critère de bascule documenté ADR 0032 §Critères : `noindex` des items
  mono-mention si le build dépasse 5 min.

### Embeddings sémantiques (P2.15, ADR 0033)

- `tools/embeddings/` (package) + CLI `tools/embed_items.py`.
- Dépend de `fastembed` (lazy-import, ~80 MB modèle BGE-small).
- DB séparée `tools/output/embeddings/embeddings.sqlite` (~6 MB pour
  2651 items).
- Multi-source via `--source all`.

### Embed audio extrait (P2.12, ADR 0036)

- YouTube `nocookie` iframe lazy-reveal au clic (RGPD-safe : aucune
  requête tierce avant interaction).
- Composant `<AudioExcerpt />` câblé automatiquement dans
  `MentionsTimeline.astro`.
- Prop `audio` optionnelle dans `<RecoCard />` (slot opt-in).

## 10. Adapter SSR & bascule `hybrid`

Le kit est livré en `output: 'static'` par défaut pour permettre un
déploiement sur n'importe quel hébergeur statique (GitHub Pages,
Netlify drop, S3, OVH static…). Seul `/api/report` requiert SSR.

### Activer SSR pour `/api/report` uniquement

1. Installer l'adapter cible :
   ```bash
   npm i @astrojs/node          # auto-host (Docker, VM, fly.io…)
   # ou : npm i @astrojs/vercel
   # ou : npm i @astrojs/netlify
   ```
2. Modifier `astro.config.mjs` :
   ```js
   import node from '@astrojs/node';
   export default defineConfig({
     output: 'hybrid',
     adapter: node({ mode: 'standalone' }),
     // … reste de la config
   });
   ```
3. Vérifier que `src/pages/api/report.ts` exporte bien
   `export const prerender = false;` (déjà présent).
4. Rebuilder : `npm run build`. Toutes les pages restent prerenderées,
   seul `/api/report` devient une route serveur.
5. Définir `REPORTS_SECRET`, `REPORTS_IP_SALT`, `TRUSTED_PROXIES`
   (cf. §8) côté hébergeur.

### Rester en `static` (fallback mailto)

1. Définir `siteConfig.contactEmail` dans `src/config/site.ts`.
2. Le `ReportForm` activera automatiquement le bouton "Envoyer par
   email" si le POST échoue (405) ou s'il n'y a pas de JS.

## 11. Pipelines multi-source

Tous les CLIs Python supportent `--source all` (boucle sur les
sources de `src/content/sources/*.json`) :

```bash
python -m tools.build_cache         --source all   # cache SQLite + FTS5
python -m tools.embed_items         --source all   # embeddings BGE
python -m tools.refresh_enrichment  --source all   # TMDB / Music
python -m tools.lint_dataset        --source all   # audit dataset
python -m tools.audit_tmdb          --source all   # audit enrichments
python -m tools.audit_yt_acast      --source all   # audit match YT/Acast
```

Cf. ADR 0001 (sources SSOT) pour la structure des fichiers source.

## 12. Docker — démarrage en une commande

Cf. ADR 0037. Le kit livre un `docker-compose.yml` à la racine pour qui
préfère ne pas installer Node + Python 3.12 + toolchain C++ en local.

### Quickstart

```bash
cp .env.example .env          # remplir TMDB_API_KEY etc. (tout est optionnel)
docker compose up             # build + review_server (8000) + site (4321)
```

Ou via `make` si dispo :

```bash
make build && make up         # idem
make ps                       # statut
make logs                     # tail
make down                     # arrêt
```

### Services

| Service | Port | Rôle |
|---------|------|------|
| `reco-review` | 8000 | `review_server.py` — relecture locale des recos |
| `reco-site`   | 4321 | site statique Astro builé (`dist/`) |
| `reco-pipeline` | — | pipeline (build_cache + lints + audits), profile opt-in |

### Pipeline (job ponctuel)

```bash
docker compose --profile pipeline run --rm reco-pipeline
# ou : make pipeline
```

### Volumes persistés

- `./src/content` ↔ `/app/src/content` : recos JSON (éditables à chaud).
- `./tools/output` ↔ `/app/tools/output` : caches SQLite, embeddings,
  audits — re-générables mais coûteux. **Ne pas effacer** sauf si tu veux
  repartir d'une base vide.

### Secrets

Le `.env` est mounté via `env_file`, jamais copié dans l'image. Le
`.dockerignore` exclut `.env`, `tools/.env`, `.env.*` (sauf
`.env.example`).

### Limites connues

- Image runtime ~600 MB (slim + venv pipeline). À monitorer si on ajoute
  `torch`/CUDA un jour.
- Le conteneur tourne en root (volumes mountés UID arbitraire). À
  rebasculer non-root si on publie l'image en registry.
- Pas de rebuild Astro depuis l'image runtime (Node absent). Pour
  régénérer `dist/` : `docker compose build` ou `./docker/build-static.sh`
  en local puis `make up`.

## 13. Poll RSS hebdomadaire + notification (P3.23, ADR 0042)

Le kit détecte automatiquement les nouveaux épisodes via le workflow
`.github/workflows/cron-rss.yml` (cron lundi 06:00 UTC) et notifie
Discord par défaut. Pour activer :

1. **Créer un webhook Discord** dans ton serveur : Paramètres du serveur
   → Intégrations → Webhooks → Nouveau webhook. Copie l'URL.
2. **Ajouter le secret** dans GitHub : Settings → Secrets and variables
   → Actions → New repository secret → `RECO_DISCORD_WEBHOOK` = URL copiée.
3. **Lancer manuellement une première fois** (workflow_dispatch) pour
   amorcer l'état hebdo et vérifier que la chaîne fonctionne.

### Tester en local (sans rien envoyer)

```bash
python tools/poll_rss.py --source un-bon-moment --dry-run --notify none --json
```

Le `--dry-run` parse le flux et affiche les nouveautés sans rien écrire
ni notifier. Le `--json` produit un résumé parseable.

### Forker vers Slack ou email

- **Slack** : créer un webhook incoming sur api.slack.com/apps. Secret
  `RECO_SLACK_WEBHOOK`. Changer `--notify` dans `cron-rss.yml`.
- **Email** : secrets `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`,
  `SMTP_FROM`, `SMTP_TO`. Changer `--notify email`.

### Comment ça marche

- Le sidecar `tools/output/rss/<source>/state.json` (gitignored) garde
  `seenGuids` (LRU borné à 10 000) + `lastEtag`/`lastModified` pour
  envoyer du conditional GET.
- Le workflow restaure cet état via `actions/cache@v4` entre runs CI.
- Idempotent : re-run sans nouveauté = aucune notification.
- Premier run sur un podcast à 300+ épisodes : `--limit-new=5` cap les
  notifs pour éviter le déluge ; les 295 autres sont quand même marqués
  vus.
- `--dispatch-event` poste un `repository_dispatch reco-new-episode`
  vers GitHub qui peut déclencher le pipeline complet (à câbler dans
  un workflow dédié — non livré).

### Critère de bascule

Si tu héberges 100+ sources, le cache GHA peut devenir limitant : passer
sur un store léger (Redis Upstash gratuit, ou commit auto dans une
branche `state/`). Cf. ADR 0042 §Critères de bascule.

## 14. Méta-mode opt-in (P4 item #24, ADR 0045)

Le « méta-site » (annuaire de podcasts Reco façon source-internet.fr)
n'est PAS un mode forké — c'est un build opt-in du kit qui agrège
plusieurs registres publics `/.well-known/reco-registry.json`. Si tu
forkes pour publier UN podcast, ignore cette section.

### Variables d'environnement

| Variable | Rôle | Défaut |
|----------|------|--------|
| `META_MODE` | `1` active le build du méta-site et expose `/meta/*` | `0` (off) |
| `META_REGISTRIES_FILE` | Chemin du fichier listant les registres à crawler | `tools/meta/registries.txt` |
| `META_BUILD_OUTPUT` | Dossier où sont écrits les snapshots agrégés | `tools/output/meta/` |

### Comportement

- `META_MODE=0` (défaut) : les routes `/meta/*` ne sont pas générées,
  zéro impact sur le fork classique. La frontière est documentée en
  ADR 0028 (boundary fork-vs-meta).
- `META_MODE=1` : crawl + build du sitemap d'annuaire + cartes podcast.
  Toutes les pages sont taguées `noindex` côté podcast indexé (le
  méta-site lui-même reste indexable).
- `/.well-known/reco-registry.json` est servi par chaque fork (kit
  exposeur) : pas besoin de `META_MODE` côté fork. Seul l'agrégateur
  active le mode.

## 15. Tracking clics sortants (P4 item #25, ADR 0046)

Mesure agrégée et anonyme des clics sortants vers TMDB, Spotify, IMDB,
YouTube, librairies indépendantes. Aucun cookie, aucun tiers — beacon
posté vers `/api/click` (SSR opt-in).

### Variables d'environnement

| Variable | Rôle | Requis |
|----------|------|--------|
| `TRACKING_IP_SALT` (≥ 16 chars) | Salt HMAC pour hash IP (rate-limit) | si SSR actif |
| `TRUSTED_PROXIES` (CSV d'IPs) | Reverse proxies autorisés à fournir `x-forwarded-for` | si derrière CDN |

### Activation

1. SSR requis (`/api/click`) : suit la même procédure que `/api/report`
   (cf. §10 — `output: 'hybrid'` + adapter).
2. Si SSR non activé : le beacon échoue silencieusement, le clic suit
   son cours normal (UX intacte).
3. Côté script global (`Layout.astro`) : le tracking est désactivé
   automatiquement sur les pages `noindex` (admin, manifeste, `/meta/*`)
   et quand `navigator.globalPrivacyControl === true`.

### Cold-start serverless (caveat)

Le rate-limit (cf. ADR 0046) utilise un cache mémoire process-local.
Sur Vercel/Netlify functions, chaque cold-start réinitialise ce cache —
un attaquant qui force des cold-starts peut contourner la limite. Pour
un usage anti-spam basique c'est acceptable ; pour un durcissement,
brancher Redis/KV (TODO documenté ADR 0046).

### Agrégation

```bash
python -m tools.aggregate_clicks --window 7d
# émet tools/output/clicks/agg-YYYY-WW.json
```

Le sidecar JSON est repris par `/stats` (cf. §16) — pas de lecture
directe en page.

## 16. Stats publiques globales (P4 item #26, ADR 0047)

Page `/stats` (globale, tous podcasts agrégés) + `/[source]/stats`
(par source). 100 % build-time, aucun JS visiteur.

### Build

```bash
# Une source
python -m tools.build_stats --source un-bon-moment
# Toutes les sources (= page /stats globale)
python -m tools.build_stats --source all
```

Sortie : `tools/output/stats/<source>.json` + `global.json`. Repris
par les pages Astro au build (import statique).

### Variables d'environnement

Aucune. Les stats sont calculées depuis le contenu local
(`src/content/`) + le cache SQLite (`tools/output/cache/`). Pas de
clé API requise.

### Comportement

- `prerender = true` (statique, cf. §17 ci-dessous).
- Si `tools/output/stats/global.json` absent au build : la page
  affiche un état vide (`stats.empty.*`).
- Couplage léger avec §15 : la colonne « clics » apparaît uniquement
  si `tools/output/clicks/*.json` existe.

## 17. `prerender` sur chaque route API/JSON

Le kit cible `output: 'static'` par défaut. Quelques routes sont
hybrides et exportent explicitement leur mode :

| Route | `prerender` | Raison |
|-------|-------------|--------|
| `src/pages/api/report.ts` | `false` | POST visiteur (SSR opt-in) |
| `src/pages/api/click.ts` | `false` | Beacon tracking (SSR opt-in) |
| `src/pages/.well-known/reco-registry.json.ts` | `true` | Manifeste public statique |
| `src/pages/meta/*` | `true` | Build conditionné `META_MODE` |
| `src/pages/stats.astro` | `true` | Build-time, sidecar JSON |
| `src/pages/[source]/stats.astro` | `true` | Build-time, sidecar JSON |

Règle d'or : toute nouvelle route API/JSON DOIT exporter `prerender`
explicitement (cf. ADR 0034, ADR 0046, ADR 0045, ADR 0047). Astro 5
warn au build static si un endpoint n'a pas de `prerender = false`
mais qu'il utilise des features SSR.

