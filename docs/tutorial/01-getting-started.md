# Tutorial 1 — Premier déploiement (5 min)

> **Objectif** : avoir le site Reco qui tourne en local en moins de 5 minutes,
> avec les données de démo *Un Bon Moment*. Aucune clé API requise pour cette étape.

## Prérequis

Choisir **une** des deux options :

### Option A — Docker (recommandé)

- Docker Desktop ≥ 24 (ou Docker Engine + Compose v2 sous Linux).
- 4 Go RAM libre.

### Option B — Local (Node + Python)

- Node.js ≥ 20 + npm ≥ 10.
- Python ≥ 3.12.
- Git.

---

## Les 5 minutes

### 1. Cloner

```bash
git clone https://github.com/etienneboursault/reco.git
cd reco
```

### 2. Configurer l'environnement

```bash
cp .env.example .env
```

`.env` est facultatif pour la démo (les clés API ne sont nécessaires qu'au
pipeline). Pour l'instant on garde tout vide.

### 3a. Lancer (Docker)

```bash
docker compose up
```

Au premier lancement, le build de l'image prend ~3 minutes.
Les fois suivantes : 5 secondes.

### 3b. Lancer (local)

```bash
npm install
npm run build      # → dist/ (site statique)
npm run dev        # → http://localhost:4321 (dev server)

# Dans un autre terminal — review server Python
python -m venv tools/.venv
tools/.venv/Scripts/activate            # Windows
# source tools/.venv/bin/activate       # Linux/Mac
pip install -r tools/requirements.txt
python tools/review_server.py --source un-bon-moment
```

### 4. Ouvrir

- Site : <http://localhost:4321>
- Review : <http://localhost:8000>

---

## Validation — checklist

- [ ] `docker compose ps` (ou `npm run dev`) tourne sans erreur.
- [ ] <http://localhost:4321> affiche le catalogue *Un Bon Moment*.
- [ ] <http://localhost:4321/un-bon-moment/> liste des recos.
- [ ] <http://localhost:8000> affiche la galerie de relecture.
- [ ] Au moins une vignette d'épisode est visible avec recos `draft`.

---

## Troubleshooting

### Port 4321 ou 8000 déjà occupé

```bash
# Docker — changer en variable d'env (compose) :
SITE_URL=http://localhost:5321 docker compose up
# Local — Astro :
npm run dev -- --port 5321
```

### `python: command not found`

Sous Windows, Python s'installe via le Store ou python.org. Vérifier :

```bash
python --version    # ≥ 3.12
```

### `Cannot find module 'astro'`

```bash
rm -rf node_modules package-lock.json
npm install
```

### Docker daemon non démarré

Lancer Docker Desktop. Sous Linux : `sudo systemctl start docker`.

### `ModuleNotFoundError: No module named 'feedparser'`

Le venv n'est pas activé. Réactiver :

```bash
tools/.venv/Scripts/activate     # Windows
source tools/.venv/bin/activate  # Linux/Mac
```

---

## Étape suivante

Maintenant que le site tourne : [Tutorial 2 — ajouter ton podcast](02-add-podcast.md).
