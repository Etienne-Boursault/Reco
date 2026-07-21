```
  ____
 |  _ \ ___  ___ ___
 | |_) / _ \/ __/ _ \
 |  _ <  __/ (_| (_) |    Curation de recommandations issues de podcasts,
 |_| \_\___|\___\___/     self-hostable et duplicable.
```

# Reco

> **Catalogue duplicable des recommandations entendues dans des podcasts.**
> Astro 5 + Python 3.12. Auto-hébergeable. Une source = un JSON.

[![CI](https://img.shields.io/badge/CI-pending-lightgrey.svg)](https://github.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](package.json)
[![Astro](https://img.shields.io/badge/Astro-5.0-orange.svg)](https://astro.build/)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org/)
[![Contributors](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Tests](https://img.shields.io/badge/tests-3186%20py%20%2F%20236%20vitest-success.svg)](#contributing)
[![Pages](https://img.shields.io/badge/pages-5793-blue.svg)](#architecture)
[![ADRs](https://img.shields.io/badge/ADRs-42-informational.svg)](docs/adr/)

---

## Quick start

```bash
git clone https://github.com/etienneboursault/reco.git && cd reco
npx reco init                 # wizard interactif (nom, slug, RSS, thème)
docker compose up             # http://localhost:4321 + review http://localhost:8000
```

Pas de Docker ? Voir [`docs/tutorial/01-getting-started.md`](docs/tutorial/01-getting-started.md).

---

## Features

- **Pipeline complet** : RSS → transcription Whisper → extraction LLM cross-validée (Anthropic + OpenAI) → enrichissement TMDB/Spotify/MusicBrainz → relecture humaine → site statique.
- **Multi-source natif** : ajouter un podcast = un fichier JSON + `--source <slug>` sur chaque CLI.
- **Wizard `reco init`** : scaffolding interactif (Node ou Python) — slug, RSS, hosts, couleurs WCAG AA.
- **Docker Compose** : `docker compose up` lance review server + site statique en une commande.
- **Liens éthiques** : évite Amazon et le groupe Bolloré, privilégie indépendants, Bandcamp, Qobuz, JustWatch.
- **Cross-LLM** : recos confirmées par 2 modèles distincts remontées en tête de pile de relecture (⭐).
- **A11y first** : tokens design WCAG AA, contrast checké en CI, pa11y-ci, fonts auto-hébergées.
- **Single-locale par fork** : i18n stricte (`src/i18n/<locale>.ts`), pas de mélange de langues côté UI.
- **Visitor reports + Search frontend** : signalements typés + recherche minisearch côté client.
- **42 ADRs** documentent les décisions structurantes (architecture, sécurité, éthique).

---

## Demo

```
  ┌─────────────────────────────────────────────────┐
  │  source-internet.fr  ▸  /un-bon-moment/         │
  ├─────────────────────────────────────────────────┤
  │  ⭐ The Bear (série)         — Kyan + Navo      │
  │  ⭐ Suzuki Method            — invité           │
  │     Le Bureau des Légendes   — Kyan             │
  │  ⭐ Bandcamp: Vulfpeck       — Navo             │
  └─────────────────────────────────────────────────┘
```

Démo publique : <https://source-internet.fr> *(placeholder)*.

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

Le site est **statique** : Netlify, Vercel, Cloudflare Pages, GitHub Pages, nginx — tout fonctionne.
Reports (POST visiteurs) nécessitent un adapter SSR (`@astrojs/node`, `output: 'hybrid'`).
Détails dans [`docs/tutorial/04-deploy-static.md`](docs/tutorial/04-deploy-static.md).

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
                     │ transcribe   │  Whisper (CPU / CUDA)
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
                     │  Astro build │  → dist/ statique
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
| [`docs/manifeste-ethique.md`](docs/manifeste-ethique.md) | Manifeste éthique du projet |
| [`docs/screencast-script.md`](docs/screencast-script.md) | Script du screencast 5 min |
| [`docs/adr/`](docs/adr/) | 42 ADRs (décisions architecture) |

---

## Contributing

Les contributions sont bienvenues. Lire d'abord :

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — workflow, conventions, tests.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — Contributor Covenant.
- [`SECURITY.md`](SECURITY.md) — signalement de vulnérabilité.

Avant tout PR :

```bash
npm run build && npm test
python -m pytest tests/ -q
```

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
  url    = {https://github.com/etienneboursault/reco}
}
```

Fichier machine-readable : [`CITATION.cff`](CITATION.cff).
