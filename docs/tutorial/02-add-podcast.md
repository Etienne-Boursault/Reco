# Tutorial 2 — Ajouter ton podcast en 5 minutes

> **Objectif** : démarrer un fork pour ton propre podcast, du wizard au déploiement.
> Équivalent texte du screencast 5 min ([script narratif](../screencast-script.md)).

---

## Étape 1 — Wizard `reco init` (1 min)

```bash
npx reco init
# ou, équivalent Python :
python -m tools.reco_init
```

Questions interactives :

```
? Nom du podcast              : Mon Podcast
? Slug (URL-safe)             : mon-podcast
? URL du flux RSS             : https://feeds.example.com/mon-podcast
? Chaîne YouTube (optionnel)  : https://youtube.com/@MaChaine
? Hôtes (séparés par virgule) : Alice, Bob
? Couleur accent (hex)        : #ff6b35
? Couleur fond (hex)          : #1a1a1f
? Couleur texte (hex)         : #e8e8e8
✓ Validation WCAG AA OK (ratio 7.21)
✓ src/content/sources/mon-podcast.json créé
```

Vérifier le fichier généré :

```bash
cat src/content/sources/mon-podcast.json
```

Si tu veux ajuster, édite directement le JSON — c'est la source unique
de vérité (SSOT, ADR 0001).

---

## Étape 2 — Fetch + transcribe (15–30 min selon catalog)

Pipeline complet (nécessite `.env` avec `ANTHROPIC_API_KEY` + `OPENAI_API_KEY`) :

```bash
docker compose --profile pipeline run --rm reco-pipeline
```

Ou pas-à-pas (cf. [Tutorial 3 — pipeline walkthrough](03-pipeline-walkthrough.md)) :

```bash
python tools/fetch_episodes.py --source mon-podcast
python tools/match_youtube.py  --source mon-podcast
python tools/transcribe.py     --source mon-podcast --all --youtube
python tools/extract_recos.py  --source mon-podcast --all --provider anthropic
python tools/extract_recos.py  --source mon-podcast --all --provider openai
```

> **Démo rapide sans Whisper** : un fichier `episodes_demo.json` est
> disponible dans `tools/fixtures/` pour court-circuiter la transcription.
> Cf. Tutorial 3 §"Mode démo".

---

## Étape 3 — Build + serve (1 min)

```bash
docker compose up
```

- Site : <http://localhost:4321/mon-podcast/>
- Review : <http://localhost:8000>

Validation : la nouvelle source apparaît dans le catalogue et tes recos
`draft` sont visibles dans le review server.

---

## Étape 4 — Personnaliser (2 min)

### Couleurs

```jsonc
// src/content/sources/mon-podcast.json
{
  "theme": {
    "accent": "#ff6b35",
    "bg":     "#1a1a1f",
    "text":   "#e8e8e8"
  }
}
```

Le wizard a déjà vérifié WCAG AA. Si tu modifies à la main :

```bash
npm run test:contrast
```

### Logo / favicon

Déposer dans `public/` :

```
public/
├── favicon.svg
├── og-image.png
└── logo-mon-podcast.svg
```

### Manifeste éthique (si fork distinct)

Éditer [`docs/manifeste-ethique.md`](../manifeste-ethique.md) pour ajuster
les principes (par exemple si tu ne suis pas la politique "éviter Amazon
et Bolloré"). Cf. [ADR 0040](../adr/0040-manifeste-ethique.md).

### Branding global (siteName, baseline, contact)

Édité dans `src/lib/siteConfig.ts`. Cf. [Tutorial 5 — customize](05-customize.md).

---

## Étape 5 — Déployer (5 min)

### Netlify drop (le plus rapide)

```bash
npm run build
# Puis glisser le dossier dist/ sur https://app.netlify.com/drop
```

### Netlify via GitHub

```toml
# netlify.toml
[build]
  command = "npm run build"
  publish = "dist"
```

### Vercel

```bash
npm i -g vercel
vercel --prod
```

### GitHub Pages

Template prêt-à-l'emploi dans [Tutorial 4 — deploy static](04-deploy-static.md#github-pages).

### Self-host nginx

Cf. [Tutorial 4 §nginx](04-deploy-static.md#self-host-nginx).

---

## Validation finale

- [ ] `src/content/sources/mon-podcast.json` existe et est valide.
- [ ] `/mon-podcast/` est visible localement.
- [ ] Au moins 5 recos `validated` après relecture.
- [ ] `npm run build` produit un `dist/` sans erreur.
- [ ] Le site déployé répond en HTTPS.

---

## Aller plus loin

- [Tutorial 3 — pipeline walkthrough](03-pipeline-walkthrough.md) — comprendre chaque étape.
- [Tutorial 5 — customize](05-customize.md) — theme, fonts, i18n.
- [Fork guide](../fork-guide.md) — checklist complète pour un fork production.
