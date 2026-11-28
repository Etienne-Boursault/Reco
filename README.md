```
  ____
 |  _ \ ___  ___ ___
 | |_) / _ \/ __/ _ \
 |  _ <  __/ (_| (_) |    Curation de recommandations issues de podcasts,
 |_| \_\___|\___\___/     self-hostable et duplicable.
```

# Reco

> **Catalogue duplicable des recommandations entendues dans des podcasts.**
> Astro 7 + Python 3.12. Auto-hébergeable. Une source = un JSON.

[![CI](https://github.com/Etienne-Boursault/Reco/actions/workflows/ci.yml/badge.svg)](https://github.com/Etienne-Boursault/Reco/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](package.json)
[![Astro](https://img.shields.io/badge/Astro-7.1-orange.svg)](https://astro.build/)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org/)
[![Contributors](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Tests](https://img.shields.io/badge/tests-6461%20pytest%20%2F%202298%20vitest-success.svg)](#contributing)
[![Pages](https://img.shields.io/badge/pages-2593-blue.svg)](#architecture)
[![ADRs](https://img.shields.io/badge/ADRs-48-informational.svg)](docs/adr/)

---

## Quick start

```bash
git clone https://github.com/Etienne-Boursault/Reco.git && cd Reco
npx reco init                 # wizard interactif (nom, slug, RSS, thème)
docker compose up             # http://localhost:4321 + review http://localhost:8000
```

Pas de Docker ? Voir [`docs/tutorial/01-getting-started.md`](docs/tutorial/01-getting-started.md).

---

## Features

- **Pipeline complet** : RSS → transcription Whisper → extraction LLM cross-validée (Anthropic + OpenAI) → enrichissement TMDB/Spotify/MusicBrainz → relecture humaine → site.
- **Multi-source natif** : ajouter un podcast = un fichier JSON + `--source <slug>` sur chaque CLI.
- **Wizard `reco init`** : scaffolding interactif (Node ou Python) — slug, RSS, hosts, couleurs WCAG AA.
- **Docker Compose** : `docker compose up` lance review server + site statique en une commande.
- **Liens éthiques** : évite Amazon et le groupe Bolloré, privilégie indépendants, Bandcamp, Qobuz, JustWatch.
- **Cross-LLM** : recos confirmées par 2 modèles distincts remontées en tête de pile de relecture (⭐).
- **A11y first** : tokens design WCAG AA, contrast checké en CI, pa11y-ci, fonts auto-hébergées.
- **Single-locale par fork** : i18n stricte (`src/i18n/<locale>.ts`), pas de mélange de langues côté UI.
- **Visitor reports + Search frontend** : signalements typés + recherche minisearch côté client.
- **48 ADRs** documentent les décisions structurantes (architecture, sécurité, éthique).

---

## Demo

```
  ┌─────────────────────────────────────────────────┐
  │  unebonnere.co  ▸  /un-bon-moment/              │
  ├─────────────────────────────────────────────────┤
  │  ⭐ The Bear (série)         — Kyan + Navo      │
  │  ⭐ Suzuki Method            — invité           │
  │     Le Bureau des Légendes   — Kyan             │
  │  ⭐ Bandcamp: Vulfpeck       — Navo             │
  └─────────────────────────────────────────────────┘
```

Instance de référence : <https://unebonnere.co> — les recommandations d'*Un Bon Moment*
(Kyan Khojandi & Navo), 1 037 œuvres pour 1 217 mentions.

---

## Installation

### Docker (recommandé)

```bash
docker compose up                              # review + site
docker compose --profile pipeline run --rm reco-pipeline
```

Cf. [ADR 0037 — Docker compose deployment](docs/adr/0037-docker-compose-deployment.md).

### Local (Node + Python)

```bash
npm install && npm run build && npm run dev   # site Astro
python -m venv tools/.venv && tools/.venv/Scripts/activate
pip install -r tools/requirements.txt         # pipeline Python
```

### Cloud

Deux modes, selon que le site doit **recevoir** quelque chose ou seulement en servir.

**Statique** — `npm run build` produit des fichiers, et n'importe quel hébergeur les sert :
Netlify, Vercel, Cloudflare Pages, GitHub Pages, nginx. Le formulaire de signalement bascule
alors sur son repli e-mail. Cf. [`docs/tutorial/04-deploy-static.md`](docs/tutorial/04-deploy-static.md).

**SSR** — nécessaire pour recevoir les signalements des visiteurs. L'adaptateur
`@astrojs/node` s'active avec `RECO_SSR=1` au build ; il reste inactif par défaut pour
que la CI et les hébergeurs statiques ne le paient pas.

```bash
RECO_SSR=1 SITE_URL=https://votre-domaine npm run build
npm start        # node --env-file-if-exists=.env ./server.mjs
```

`server.mjs` sert `dist/client` et compresse — `@astrojs/node` ne le fait pas, et sans lui
la page d'accueil part en 2,6 Mo au lieu de 200 Ko.

**Fréquentation** — en SSR, chaque requête traverse `server.mjs` : le site peut se mesurer
lui-même, sans tracker tiers, sans cookie et sans service extérieur. `/audience` lit ces
mesures. Depuis AU-2 B (27/11/2026), le navigateur garde une seule entrée de stockage local,
`reco.mesure` (date de première visite, étapes vues le jour même, état de la ligne
d'information ; 13 mois sans prolongation) : elle ne quitte jamais le navigateur, seuls trois
oui/non (déjà venu, a vu un épisode, a vu une fiche le jour même) accompagnent le signal
« page vue » et le clic. Un refus en un clic dans le pied de page, Global Privacy Control et
Do Not Track coupent ces envois ; le serveur compte toujours la page servie. L'empreinte d'un
jour est un pseudonyme (avec le sel et une adresse IP, on la recalcule). Les mentions légales
(`src/pages/mentions-legales.astro`) décrivent chaque champ écrit, et un test les relit contre
le code. Trois variables activent la mesure ; sans elles la page répond 404 et rien
d'identifiable n'est écrit :

| Variable | Rôle | Sans elle |
|---|---|---|
| `RECO_AUDIENCE_KEY` | ouvre `/audience?cle=…` (≥ 16 signes), et `GET /api/bord` avec la même clé dans l'en-tête `X-Reco-Cle` | la page et le point d'accès n'existent pas (404) |
| `RECO_AUDIENCE_SALT` | sale l'identifiant de visiteur du jour (≥ 16 signes) | les pages sont comptées, pas les visiteurs |
| `RECO_SOURCES` | les sources mesurées, ex. `un-bon-moment` | aucun chemin n'est rattaché à une source |
| `RECO_AUDIENCE_EXCLURE` | adresses de l'éditeur à ne pas mesurer : noms d'hôte (DNS dynamique) et adresses IP, séparés par des virgules ; les noms sont résolus au démarrage puis toutes les 5 min ; les plages (`203.0.113.0/24`) ne sont pas prises en charge : une entrée avec `/` est refusée et signalée dans le journal | rien n'est exclu |

Une requête venue d'une adresse exclue n'écrit ni visite, ni signal « page vue », ni clic.
Une visite depuis un autre réseau (mobile) compte ; les mesures déjà écrites ne sont pas
corrigées ; une adresse qui change compte encore au plus 5 min, plus le délai du DNS dynamique.

La clé transite dans l'URL pour qu'un signet suffise : c'est un secret partagé, du niveau
d'un lien non listé, **pas** une authentification. Ce que la mesure retient et ce qu'elle
jette est détaillé dans [`src/lib/audience/derive.mjs`](src/lib/audience/derive.mjs).

**`GET /api/bord`** (tableau de bord, 27/11/2026) rend en JSON ce que le tableau de bord de
la relecture affiche : sur 7 et sur 30 jours, les visiteurs-jours et visites confirmés,
incertains et robots (ou « ancien tri » avant la bascule), les 7 jours un par un, les 5
premières pages et provenances, les clics pour 100 visiteurs, et les signalements en attente
(identifiant, reco, catégorie, date ; **jamais** le nom, l'adresse ni le texte). Les chiffres
sont ceux de `/audience`, par la même lecture (`src/lib/audience/vue.ts`). La clé passe dans
l'en-tête `X-Reco-Cle`, jamais dans l'URL ; sans elle, ou pour une autre méthode que GET, la
réponse est un 404, jamais mise en cache. Comme `/audience`, la route n'existe qu'avec
`RECO_SSR=1`, et la mesure ne compte pas les appels sous `/api/`. Le détail :
[`src/lib/bord/resume.ts`](src/lib/bord/resume.ts).

Le **pays** vient d'un en-tête de l'hébergeur quand il en pose un, sinon d'une table
embarquée — aucune requête sortante, aucun tiers. Chez un hébergeur inconnu, commencer par
regarder ce qui arrive vraiment : `/audience?cle=…&entetes=1` liste les en-têtes reçus.
La table se rafraîchit ainsi, et n'a pas besoin de l'être souvent :

```bash
python tools/construire_table_pays.py        # ~2 Mo, écrit src/lib/audience/pays-ip.bin.gz
```

Sans elle le reste fonctionne : seul le pays manque, et la page le dit.

L'instance de référence tourne sur un **site Node.js Infomaniak**, déployé
automatiquement : [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) se déclenche
quand la CI passe au vert sur `main`, lance la construction chez l'hébergeur, puis **vérifie
que le commit attendu est réellement en ligne** avant de conclure. Il l'a fallu : trois
versions successives annonçaient un succès sur une production restée trois semaines en arrière.

> ⚠️ Une dépendance nécessaire au **build** doit être en `dependencies`, jamais en
> `devDependencies` : l'hébergeur installe avec `npm ci --omit=dev`. Les polices
> `@fontsource/*`, importées par `src/styles/global.css`, ont ainsi mis le site hors ligne
> quarante minutes.

---

## Architecture

```
        RSS                YouTube
         │                    │
         ▼                    ▼
   ┌──────────┐         ┌──────────┐
   │  fetch   │────────▶│  match   │
   └──────────┘         └─────┬────┘
                              ▼
                     ┌──────────────┐
                     │ transcribe   │  Whisper large-v3 (CPU / CUDA)
                     └──────┬───────┘
                            ▼
                     ┌──────────────┐
                     │  extract     │  Anthropic + OpenAI
                     └──────┬───────┘  ⭐ cross-validé
                            ▼
                     ┌──────────────┐
                     │   enrich     │  TMDB + Spotify + MusicBrainz
                     └──────┬───────┘
                            ▼
                     ┌──────────────┐
                     │   review     │  review_server.py — port 8000
                     └──────┬───────┘
                            ▼
                     ┌──────────────┐
                     │ build cache  │
                     └──────┬───────┘
                            ▼
                     ┌──────────────┐
                     │  Astro build │  → dist/client + dist/server
                     └──────┬───────┘
                            ▼
                     ┌──────────────┐
                     │   server     │  server.mjs — statiques + gzip
                     └──────┬───────┘
                            ▼
                     ┌──────────────┐
                     │  déploiement │  CI verte → build hébergeur → vérifié
                     └──────────────┘
```

Vue détaillée : [`docs/architecture.md`](docs/architecture.md).

---

## Documentation

| Fichier | Contenu |
|---|---|
| [`docs/index.md`](docs/index.md) | Table des matières documentation |
| [`docs/tutorial/01-getting-started.md`](docs/tutorial/01-getting-started.md) | Premier déploiement en 5 minutes |
| [`docs/tutorial/02-add-podcast.md`](docs/tutorial/02-add-podcast.md) | Ajouter ton podcast (équivalent du screencast 5 min) |
| [`docs/tutorial/03-pipeline-walkthrough.md`](docs/tutorial/03-pipeline-walkthrough.md) | Pipeline pas-à-pas |
| [`docs/tutorial/04-deploy-static.md`](docs/tutorial/04-deploy-static.md) | Déployer (Netlify, Vercel, Pages, self-host) |
| [`docs/tutorial/05-customize.md`](docs/tutorial/05-customize.md) | Personnaliser (theme, fonts, i18n) |
| [`docs/architecture.md`](docs/architecture.md) | Vue d'ensemble système |
| [`docs/fork-guide.md`](docs/fork-guide.md) | Forker pour son podcast |
| [`docs/pieges-et-echecs.md`](docs/pieges-et-echecs.md) | **Ce qui n'a pas marché** — à lire avant de lancer le pipeline |
| [`docs/manifeste-ethique.md`](docs/manifeste-ethique.md) | Manifeste éthique du projet |
| [`docs/screencast-script.md`](docs/screencast-script.md) | Script du screencast 5 min |
| [`docs/adr/`](docs/adr/) | 48 ADRs (décisions architecture) |

---

## Contributing

Les contributions sont bienvenues. Lire d'abord :

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — workflow, conventions, tests.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — Contributor Covenant.
- [`SECURITY.md`](SECURITY.md) — signalement de vulnérabilité.

Avant tout PR — ce sont les commandes que la CI exécute :

```bash
npx astro check                 # types (invisible pour `astro build`)
npm run build                   # SITE_URL requis si RECO_SSR=1
npm run test:coverage           # vitest + seuil de couverture
ruff check tools/ tests/ scripts/
pytest tests/ -q --cov=tools --cov-branch
python scripts/check_coverage.py --min 95
```

`astro check` mérite son passage : `astro build` ne vérifie pas les types et laisse
passer des erreurs que la CI, elle, refuse.

---

## License

[MIT](LICENSE) — fork, modifie, déploie librement.

> **Attribution demandée** (non requise) : si vous forkez, garder un lien
> vers le projet en footer aide la communauté à grossir. Voir [`NOTICE`](NOTICE).

---

## Citation

```bibtex
@software{boursault_reco_2026,
  author = {Boursault, Étienne},
  title  = {Reco — curation de recommandations issues de podcasts},
  year   = {2026},
  url    = {https://github.com/Etienne-Boursault/Reco}
}
```

Fichier machine-readable : [`CITATION.cff`](CITATION.cff).
