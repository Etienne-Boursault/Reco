# Tutorial 5 — Personnaliser ton fork

> **Objectif** : adapter theme, branding, fonts, i18n et a11y.
> Cf. [ADR 0028 — Frontière fork-perso / kit](../adr/0028-fork-personalization-boundary.md).

## Theme — couleurs WCAG AA

### Source de vérité

```jsonc
// src/content/sources/<slug>.json
{
  "theme": {
    "accent": "#ff6b35",     // CTAs, liens
    "bg":     "#1a1a1f",     // fond page
    "text":   "#e8e8e8"      // texte principal
  }
}
```

### Validation contrast

```bash
npm run test:contrast
```

Le test échoue si un ratio est < 4.5 (texte normal) ou < 3.0 (gros texte).
Cf. [ADR 0022 — a11y WCAG AA](../adr/0022-a11y-wcag-aa.md).

### Design tokens (avancé)

`src/lib/tokens.ts` expose la palette complète. À éditer si tu veux
changer la grammaire visuelle au-delà des 3 couleurs source.
Cf. [ADR 0030 — design tokens theming](../adr/0030-design-tokens-theming.md).

---

## Branding — `siteConfig.ts`

```ts
// src/lib/siteConfig.ts
export const siteConfig = {
  siteName: 'Source Internet',
  baseline: 'Le catalogue des recos de podcasts',
  contactEmail: 'contact@source-internet.fr',
  twitter: '@source_internet',
  defaultOgImage: '/og-image.png',
};
```

Les composants `Footer.astro`, `Header.astro`, `Seo.astro` lisent ce module.

---

## Fonts — `@fontsource/inter`

Le kit utilise **Inter** auto-hébergée via `@fontsource/inter` (déjà en
dépendance). Cf. [ADR 0029 — fonts auto-hébergées](../adr/0029-fonts-embedded-licenses.md).

> ⚠️ **Ne pas ajouter Google Fonts.** Le manifeste éthique interdit le
> tracking par fonts externes. Pour changer de fonte, utiliser un autre
> paquet `@fontsource/<font>` (licences OFL/Apache).

### Changer de fonte

```bash
npm uninstall @fontsource/inter
npm install @fontsource/jetbrains-mono
```

Puis dans `src/styles/global.css` :

```css
@import '@fontsource/jetbrains-mono/400.css';
@import '@fontsource/jetbrains-mono/700.css';

:root { --font-body: 'JetBrains Mono', monospace; }
```

---

## i18n — single-locale par fork

[ADR 0025](../adr/0025-locales-i18n.md) : **un fork = une locale**.
Pas de switch user-facing, pas de mélange FR/EN dans la même UI.

```ts
// src/i18n/fr.ts (par défaut)
export const t = {
  'home.title': 'Le catalogue des recos',
  'episode.recos': 'Recommandations',
  'reco.recommendedBy': 'Recommandé par',
  // ...
};
```

Pour un fork anglais : créer `src/i18n/en.ts`, et dans `src/lib/i18n.ts` :

```ts
import { t } from '../i18n/en.ts';
export { t };
```

Toutes les chaînes UI passent par `t['<key>']`.

---

## A11y — checks automatiques

```bash
npm run test:a11y          # pa11y-ci sur dist/
npm run test:contrast      # WCAG AA contrast checker
npm run test:a11y:all      # build + pa11y + contrast
```

CI bloque en cas de violation. Cf. [ADR 0024 — CI quality gates](../adr/0024-ci-quality-gates.md).

---

## Manifeste éthique

Si ton fork diverge des principes (liens éthiques, vie privée, IA…),
mettre à jour [`docs/manifeste-ethique.md`](../manifeste-ethique.md) **et**
le lien en footer du site.

Le kit livre des défauts opinionés :
- évite Amazon et le groupe Bolloré.
- privilégie libraires indépendants, Bandcamp, Qobuz, JustWatch.
- pas de tracking, pas de cookie tiers.

Tu peux les retirer/durcir/relâcher — mais documente la divergence
dans ton manifeste pour transparence.

---

## Frontière fork-perso vs kit

[ADR 0028](../adr/0028-fork-personalization-boundary.md) liste précisément :

- **Zone fork-perso** (éditer librement) : `src/content/sources/*.json`,
  `src/lib/siteConfig.ts`, `public/`, `docs/manifeste-ethique.md`.
- **Zone kit** (éviter de toucher pour faciliter le rebase upstream) :
  `tools/`, `src/lib/tokens.ts`, `src/pages/`, `src/components/`.

Si tu touches au cœur du kit, isoler dans des composants/modules
override-ables plutôt que d'éditer les sources upstream.

---

## Reference

- [Fork guide complet](../fork-guide.md) — checklist exhaustive.
- [Manifeste éthique](../manifeste-ethique.md).
- ADRs : [0022](../adr/0022-a11y-wcag-aa.md), [0025](../adr/0025-locales-i18n.md), [0028](../adr/0028-fork-personalization-boundary.md), [0029](../adr/0029-fonts-embedded-licenses.md), [0030](../adr/0030-design-tokens-theming.md), [0040](../adr/0040-manifeste-ethique.md).
