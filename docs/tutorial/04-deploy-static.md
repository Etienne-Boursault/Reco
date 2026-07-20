# Tutorial 4 — Déployer le site

> **Objectif** : déployer le site Astro statique vers Netlify, Vercel,
> Cloudflare Pages, GitHub Pages ou nginx self-host. Reports POST = adapter SSR.

## Pré-requis

```bash
npm run build      # produit dist/
ls dist/index.html # validation
```

---

## Netlify

### Drag & drop (le plus rapide)

1. `npm run build`
2. Aller sur <https://app.netlify.com/drop>
3. Glisser `dist/`. Tu as un sous-domaine `*.netlify.app` en 30 secondes.

### Via GitHub

`netlify.toml` à la racine :

```toml
[build]
  command = "npm run build"
  publish = "dist"

[build.environment]
  NODE_VERSION = "20"

[[redirects]]
  from = "/*"
  to = "/404.html"
  status = 404
```

Connecter le repo dans Netlify → done.

---

## Vercel

```bash
npm i -g vercel
vercel --prod
```

Vercel détecte Astro automatiquement. Variables d'environnement à passer
dans le dashboard si tu utilises l'API Reports (cf. plus bas).

---

## Cloudflare Pages

1. Dashboard Cloudflare → Pages → Connect to Git.
2. Build command : `npm run build`.
3. Build output : `dist`.
4. Node version : `20`.

---

## GitHub Pages

`.github/workflows/pages.yml` (template) :

```yaml
name: Deploy to GitHub Pages
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

Activer Pages dans Settings → Pages → Source = GitHub Actions.

> Si le site n'est pas servi à la racine du domaine, ajouter `base: '/repo-name'`
> dans `astro.config.mjs`.

---

## Self-host nginx

### Config minimale

```nginx
server {
    listen 80;
    server_name source-internet.fr;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name source-internet.fr;

    ssl_certificate     /etc/letsencrypt/live/source-internet.fr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/source-internet.fr/privkey.pem;

    root /var/www/reco/dist;
    index index.html;

    # Cache des assets immutables
    location /_astro/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # HTML pas de cache (revalidation rapide)
    location / {
        try_files $uri $uri/ $uri.html =404;
        add_header Cache-Control "public, max-age=300, must-revalidate";
    }

    # 404 custom Astro
    error_page 404 /404.html;
}
```

### Déploiement

```bash
rsync -avz --delete dist/ user@server:/var/www/reco/dist/
```

---

## Avec adapter SSR (reports POST)

Si tu actives les visitor reports (POST `/api/reports`), il te faut un
runtime Node ou Edge — pas du statique pur. Cf. [ADR 0034](../adr/0034-visitor-reports.md).

### Installer l'adapter Node

```bash
npx astro add node
```

`astro.config.mjs` :

```js
import node from '@astrojs/node';

export default defineConfig({
  output: 'hybrid',          // statique par défaut, opt-in dynamique
  adapter: node({ mode: 'standalone' }),
});
```

Sur les pages dynamiques :

```astro
---
export const prerender = false;     // force le mode SSR
---
```

### Plateformes compatibles SSR

| Plateforme | Adapter | Notes |
|---|---|---|
| Vercel | `@astrojs/vercel` | Serverless functions auto. |
| Netlify | `@astrojs/netlify` | Idem. |
| Cloudflare | `@astrojs/cloudflare` | Workers. |
| Node self-host | `@astrojs/node` | systemd + reverse proxy. |

### Variables d'environnement pour reports

```dotenv
REPORTS_SECRET=<32-byte random>
REPORTS_REQUIRE_SECRET=true
REPORTS_IP_SALT=<16-byte random>
TRUSTED_PROXIES=10.0.0.0/8,nginx-ip
```

---

## Étape suivante

[Tutorial 5 — personnaliser](05-customize.md).
