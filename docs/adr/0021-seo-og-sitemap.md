# ADR 0021 — SEO : OG cards build-time + sitemap + meta enrichies

- Statut : **Acceptée — implémentée + révision CR senior/archi** (Phase 2, item P2.13, livraison 2026-06-10, durcissement 2026-06-10)
- Date : 2026-06-10
- Décideurs : équipe Reco
- ADRs liés : ADR 0030 (tokens UI), ADR 0026 (tokens partagés UI+OG), ADR 0027 (JSON-LD mapping), ADR 0028 (frontière fork), ADR 0029 (polices embarquées)

## Contexte

Reco vise une audience publique (`source-internet.fr`). La qualité du
partage social (Facebook, LinkedIn, Twitter/X, WhatsApp, Slack, Discord…)
et de l'indexation moteur conditionne directement le trafic entrant. Avant
P2.13, le site exposait :

- `<title>`, `description`, `og:title`, `og:description`, `twitter:card` —
  via `Layout.astro` (déjà solide grâce à la base posée en Phase 1).
- Une image OG **statique** (`/og-default.png`, fichier unique non
  généré) — donc identique pour les 100+ pages d'épisode.
- Un `robots.txt` **hardcodé** dans `public/` avec un domaine de repli
  (`reco.example`).
- Un `sitemap-index.xml` correct via `@astrojs/sitemap`.

Trois lacunes bloquantes pour le partage social et le SEO :

1. **Pas d'image OG dynamique** : tous les partages affichent la même
   miniature générique → faible CTR, faible reconnaissance de marque.
2. **Pas de JSON-LD** ni de `og:site_name` → les rich results Google
   (carrousel d'épisodes, badges schema.org) ne sont pas activables.
3. **Pas de `hreflang`** → ambiguïté de localisation (le site est FR-only
   en initial, mais Google ne le sait pas explicitement).

## Décision

### 1. OG cards via Satori build-time

Générer une image OG (1200×630, PNG) par page indexable au moment
d'`astro build`, via la pipeline **Satori → SVG → resvg → PNG**.

- Template centralisé : `src/lib/og/template.ts` (JSX-as-object — pas de
  JSX transpilation requise, l'objet est passé directement à Satori).
- Renderer : `src/lib/og/renderer.ts` (charge la police Inter depuis
  `src/fonts/og/` — cf. ADR 0029 — et la met en cache via **promesse**
  mémoïsée pour éviter une race condition en `Promise.all`).
- Endpoint : `src/pages/og/[...slug].png.ts` — déclare un
  `getStaticPaths` qui balaie les collections `sources` et `episodes`.

Slugs produits :
- `/og/default.png` — carte de repli (homepage et toute page sans
  override) ;
- `/og/<source>.png` — page d'un podcast/source ;
- `/og/<source>/episode/<guid>.png` — page d'un épisode (slug-safe via
  `safeSlugSegment()` aligné avec la route Astro `[guid].astro`).

L'image est référencée dans `<meta property="og:image">` via le paramètre
optionnel `ogSlug` du `Layout.astro` (câblage REPORTÉ Fixer coordination
Vague 1). Si une page fournit explicitement un `ogImage` (ex. thumbnail
YouTube `i.ytimg.com/vi/...`), celui-ci a priorité — Satori ne remplace
pas une vraie miniature vidéo. **Décision sur épisodes avec thumbnail YT** :
on ne génère **pas** de carte OG si l'épisode a une thumbnail YouTube
(skip dans `getStaticPaths` lors du câblage) — économie build + meilleur
visuel social. À retravailler quand le câblage sera fait.

#### 1.bis Cache disque OG (CR senior H6 / archi P2-A)

`renderer.ts` cache chaque PNG sous `dist/.cache/og/<sha256(input)>.png`.
Un build récurrent qui ne change pas un titre n'invoque pas Satori →
gain ~95 % sur builds incrémentaux. Invalidation : hash inclut tous
les `OGTemplateInput` champs + width/height.

#### 1.ter Version-busting OG

Quand le template OG évolue (ajout d'un élément visuel, changement de
typographie), le hash de `OGTemplateInput` reste stable mais l'output
change. Procédure manuelle : supprimer `dist/.cache/og/` + relancer
le build + purger l'OG Debugger Facebook / Twitter Card Validator.
Pas d'invalidation automatique — un fork qui touche le template doit
être conscient de ce step.

#### 1.quater Fallback Satori (CR senior H2)

Si Satori plante (titre kanji-only sans glyph couvrant, pile de
mémoire…), le renderer retourne un PNG 1×1 transparent et logge sur
stderr. Le build ne s'arrête pas pour une carte fautive. La carte
problématique sera identifiée par le log + image vide repérable sur
la home (cas hors-champ par défaut).

### 2. Sitemap

On **conserve** `@astrojs/sitemap` (déjà installé) : c'est l'intégration
officielle, maintenue, qui produit un `sitemap-index.xml` + `sitemap-N.xml`
conformes au schéma 0.9. La création d'un endpoint `sitemap.xml.ts` aurait
été redondante. Le filtre actuel exclut `/verifier` via
`page.endsWith('/verifier') || page.endsWith('/verifier/')` (filtre
robuste, cf. CR senior C3 — `includes('/verifier')` était fragile).
Métadonnées par-URL : `lastmod` (date du build), `changefreq: weekly`,
`priority: 0.7`. Une bascule par-URL nécessiterait un `serialize:` qui
lit `episode.data.publishedAt` (cf. § Critères de bascule).
Les routes non-HTML (PNG OG) sont automatiquement ignorées par
l'intégration.

Limites connues : `@astrojs/sitemap` auto-split à 45 000 URLs (configurable
via `entryLimit`). Pour Reco actuel (100-500 URLs), aucun split. Si
le site dépasse 45 k URLs, augmenter `entryLimit` ou laisser l'auto-split
publier plusieurs `sitemap-N.xml`.

### 3. robots.txt dynamique

`public/robots.txt` (hardcodé) → `src/pages/robots.txt.ts` qui lit
`Astro.site` et compose le `Sitemap:` absolu en cohérence avec le
déploiement (Netlify / Vercel / GitHub Pages — `site` est piloté par
`SITE_URL` en environnement, cf. `astro.config.mjs`).

Format minimal (cf. CR senior C4 — `Allow: /` était redondant) :
```
User-agent: *
Disallow: /*/verifier

Sitemap: <site>/sitemap-index.xml
```

Endpoint dynamique vs fichier static `public/robots.txt` : on garde
l'endpoint car le `Sitemap:` doit pointer vers une URL absolue calculée
à partir de `Astro.site` qui n'est connue qu'au build (variable selon
preview/prod).

### 4. MetaTags.astro — composant isolé

Extraction de la logique `<head>` SEO de `Layout.astro` dans un composant
dédié `src/components/MetaTags.astro`. Permet :
- d'ajouter `og:site_name`, `hreflang fr`, `hreflang x-default`,
  `twitter:url`, `twitter:site`, `twitter:creator` sans gonfler le layout ;
- d'embarquer un JSON-LD optionnel (`<script type="application/ld+json">`)
  via une prop `jsonLd` (objet ou tableau), **échappé** via `safeJsonLd()`
  contre l'injection `</script>` (CR senior C2) ;
- prop `alternates: Array<{hreflang,href}>` pour i18n futur (déduplique
  contre les `fr/x-default` émis par défaut) ;
- prop `appendSiteName` pour contrôler explicitement le suffixe
  `— {siteName}` (heuristique `endsWith` plus fragile écartée, cf. L5) ;
- de tester le rendu via Astro Container API (test unitaire isolé).

### 5. SITE_URL — fail-fast en production (CR senior H10)

`astro.config.mjs` `throw` si `NODE_ENV=production` (ou `CI=true`) et
`SITE_URL` absent. Un build CI/CD avec placeholder `reco.example`
n'est plus possible silencieusement. Un test post-build vérifie en
plus l'absence du token `reco.example` dans `dist/index.html` quand
`SITE_URL` est configuré (sécurité ceinture-bretelles).

### 6. Personnalisation (forks)

`src/config/site.ts` centralise siteName, baseline, domaineLabel,
défauts OG. Cf. ADR 0028. Couleurs lues depuis `src/styles/tokens.ts`
(SSOT UI partagée, cf. ADR 0026). Forker = 3 fichiers (config, tokens,
sources).

### 7. JSON-LD — factories typées (CR senior H9 / archi P1-C)

`src/lib/seo/jsonld.ts` expose `safeJsonLd`, `recoToSchema`,
`episodeToSchema`, `sourceToPodcastSchema` + mapping `RECO_TYPE_TO_SCHEMA`
(cf. ADR 0027). Câblage dans les pages : **REPORTÉ Fixer coordination
finale Vague 1** (zone Layout/pages).

### 8. Cache-Control PNG OG (CR senior H4)

L'endpoint OG **n'émet plus** de `Cache-Control` — en build statique,
les headers viennent du serveur (`_headers` Netlify, `vercel.json`,
nginx). Émettre un header dans l'endpoint donnait l'illusion d'être
appliqué. Documentation `_headers` à intégrer dans Deploy doc (hors
ADR).

## Alternatives écartées

| Option | Pourquoi écartée |
|--------|------------------|
| **OG runtime (Vercel OG, Cloudflare Workers)** | Coût récurrent, dépendance plateforme, latence cache miss. **Self-hostable = pas de dépendance runtime propriétaire** (CR senior M11). Le site est statique : pas de raison de payer un runtime pour un asset immuable entre deux builds. |
| **Images OG pré-faites en design tool** | Ne scale pas avec 100+ épisodes, pas de génération automatique sur ajout. |
| **Pas d'OG card du tout** | Perte d'engagement social mesurable (typiquement -30 à -50 % de CTR sans `summary_large_image`). |
| **Sitemap maison `sitemap.xml.ts`** | Réinvente la roue ; `@astrojs/sitemap` couvre déjà 100 % du besoin avec filtre `verifier`. |
| **JSX/TSX pour le template Satori** | Aurait nécessité d'ajouter un loader TSX à la chaîne Astro ; l'objet plain est strictement équivalent côté Satori. |
| **Embarquer Noto Emoji** | +1.5 MB de WOFF pour un gain visuel marginal (les emojis textuels sont compris par les humains). Reporté à un futur ADR si besoin. |

## Conséquences

### Positives
- **Zéro coût runtime** — les PNG vivent dans `dist/og/` et sont servis
  comme n'importe quel asset.
- **Atomique** — chaque build régénère un état cohérent OG ↔ HTML.
- **Reproductible** — police commit explicite, pas de réseau au build.
- **Performance** — ≈ 220 ms par carte sur la première génération
  (Satori NAPI), cache disque ⇒ ~5 ms en hit.
- **Schema.org-ready** — factories typées prêtes à l'emploi.
- **Hreflang fr / x-default** — signal clair pour Google que le site est
  monolingue FR (cohérent avec la vision initiale). Prop `alternates`
  prête pour i18n.
- **Anti-XSS** — `safeJsonLd` ferme la classe d'injection `</script>`.

### Négatives / risques
- **Rebuild OG** sur chaque changement de titre d'épisode ou de source
  → coût build linéaire (~200 ms × N épisodes). Pour ≈ 100 épisodes :
  +25 s sur le build total (≈ 1 s après mise en place du cache disque
  sur builds incrémentaux).
- **Dépendance native** : `@resvg/resvg-js` embarque un binaire natif
  (skia/resvg-rust). Sensible aux changements de plateforme CI.
  Mitigation : `npm rebuild` ou `npm install --include=optional` en CI
  cross-OS. Tester sur Linux x64 (Netlify) + macOS arm64 (dev).
- **Emojis non rendus visuellement** : Satori ne charge pas la table
  emoji par défaut. Volontairement non câblé : le glyph emoji apparaît
  textuellement (".notdef" tofu), et c'est suffisant pour différencier
  les cartes — la hiérarchie visuelle repose sur le titre + l'accent
  de couleur de la source, pas sur le glyph.

## Critères de bascule

Si une de ces conditions devient vraie, ouvrir un nouvel ADR :

- `astro build` > 5 min uniquement à cause du rendu OG → ajouter un
  cache distribué (le cache disque actuel est par-machine ; un cache
  partagé `s3://` ou GHA cache résoudrait).
- Multi-langue (EN + FR) → étendre `hreflang` + variantes de cartes OG
  + utiliser la prop `alternates` de `MetaTags`.
- Besoin de rendu emoji unicolore → câbler `loadAdditionalAsset` Satori
  sur la fonte Noto Emoji embarquée.
- Pages /item/<id> ajoutées (Dev #10/#11 futurs) → étendre
  `getStaticPaths` de l'endpoint OG. **Obligation** : un test post-build
  vérifie que toute URL `og:image` existe physiquement dans `dist/og/`
  (cross-check anti-404, CR archi P1-A — voir `test_meta_tags_build.test.ts`).
- 500+ épisodes → revoir le seuil de `entryLimit` sitemap + envisager
  partitionnement par-source.
- `lastmod` par-URL devient utile pour le SEO → ajouter `serialize:`
  qui lit `episode.data.publishedAt`.

## CSP (Content Security Policy) — note Phase 3

Le JSON-LD inline impose `script-src 'unsafe-inline'` ou un hash
SHA256 du script par page. Quand une CSP stricte sera mise en place
(Phase 3, hardening prod) :
- option A : calculer le SHA256 du `safeJsonLd(data)` côté Astro et
  l'injecter dans le header CSP (complexe car le payload varie) ;
- option B : héberger le JSON-LD dans un fichier statique `*.jsonld.json`
  référencé par `<link rel="alternate" type="application/ld+json">`
  (downgrade — Google le lit moins fiablement) ;
- option C : retirer JSON-LD inline. Décision repoussée au Phase 3.

## KPI SEO de suivi (post-livraison)

À tracker mensuellement via Google Search Console + Plausible :

| Métrique | Seuil de surveillance |
|----------|------------------------|
| Impressions / mois | Trend (∅ baseline initial) |
| CTR moyen (toutes pages) | > 2 % cible, alerter si < 1 % |
| Pages indexées | > 90 % des URLs `sitemap-0.xml` |
| Coverage errors GSC | 0 critique, < 5 warnings |
| Partages sociaux (LI/X) avec preview correcte | spot check mensuel |

**Date de prochaine revue** : 2027-06-10 (1 an post-livraison) OU à
500 épisodes catalogués, le premier des deux.

## Métriques de livraison (build 2026-06-10, post-durcissement CR)

| Métrique | Valeur |
|----------|--------|
| OG cards générées | 106 (1 default + 1 source + 104 épisodes) |
| Taille moyenne PNG | 80.8 KB |
| Taille totale `/dist/og/` | 8.4 MB |
| Durée moyenne rendu (cold) | ≈ 220 ms / carte |
| Durée moyenne rendu (cache hit) | ≈ 5 ms / carte |
| Surcoût build total (cold) | ≈ 25 s |
| Surcoût build total (incr.) | ≈ 1-2 s |
| URLs sitemap-0.xml | 106 |
| Tests SEO/OG (vitest) | ~45 verts (post-CR — était 24) |
| Tests pytest (régression) | inchangés (zone Python intacte) |

## Fichiers livrés

Nouveaux :
- `src/lib/og/template.ts`
- `src/lib/og/renderer.ts`
- `src/lib/seo/jsonld.ts`         *(post-CR)*
- `src/lib/theme/tokens.ts`        *(post-CR — indirection)*
- `src/config/site.ts`             *(post-CR — frontière fork)*
- `src/pages/og/[...slug].png.ts`
- `src/components/MetaTags.astro`
- `src/pages/robots.txt.ts`
- `src/fonts/og/{README.md, *.woff}` *(post-CR — ADR 0029)*
- `vitest.config.ts`
- `tests/og/test_og_template.test.ts`
- `tests/og/test_og_render.test.ts`
- `tests/seo/test_robots.test.ts`
- `tests/seo/test_meta_tags_build.test.ts`
- `tests/seo/test_meta_tags_unit.test.ts` *(post-CR — Container API)*
- `tests/seo/test_sitemap_build.test.ts`
- `tests/seo/test_jsonld.test.ts`  *(post-CR)*
- `docs/adr/0021-seo-og-sitemap.md`
- `docs/adr/0026-tokens-theme-shared-ui-og.md` *(post-CR)*
- `docs/adr/0027-jsonld-schema-mapping.md`     *(post-CR)*
- `docs/adr/0028-fork-personalization-boundary.md` *(post-CR)*
- `docs/adr/0029-fonts-embedded-licenses.md`   *(post-CR)*

Modifiés (minimaux) :
- `src/layouts/Layout.astro` — délègue à `<MetaTags>`, ajoute props
  `ogSlug` et `jsonLd` (câblage `ogSlug` et JSON-LD effectif REPORTÉ).
- `astro.config.mjs` — `SITE_URL` fail-fast, sitemap `lastmod/changefreq`,
  filtre `verifier` robuste.
- `package.json` — `@fontsource/inter` passé en devDep, scripts
  `test:seo` + `test:og`.

Supprimé :
- `public/robots.txt` — remplacé par l'endpoint dynamique.

## Coordination finale 2026-06-11 (Fixer coordination Vague 1)

Les zones partagées (Layout + pages) étaient verrouillées par P2.14 (a11y).
Une fois P2.14 livré, ce fixer a câblé les modules SEO laissés en attente
par P2.13 et corrigé les issues C1 / H9 / H10 / L12 / M21+.

### Changements

| Issue | Statut | Résumé |
|-------|--------|--------|
| **C1** — `ogSlug` dead code | ✅ | Câblé dans `[source]/index.astro` (`ogSlug={source.id}`) et `[source]/episode/[guid].astro` (`ogSlug={source.id}/episode/${guid}`). Le `Layout.astro` priorise déjà `ogImage` (thumb YT) quand fourni. |
| **P2-P** — skip OG cards orphelines | ✅ | `src/pages/og/[...slug].png.ts` : `getStaticPaths` skip désormais les épisodes ayant une miniature YouTube (`/[?&]v=([\w-]+)/.test(youtubeUrl)`). Économie ≈ 103 PNG × ~80 KB ≈ 8 MB. |
| **H9 / P1-C** — JSON-LD factories non câblées | ✅ | `episodeToSchema` + `recoToSchema` câblés sur la page épisode ; `sourceToPodcastSchema` + `BreadcrumbList` sur la page source ; `WebSite` sur la home. Pages reçoivent un objet ou un tableau via la prop `jsonLd` de `Layout`. |
| **H10** — test "no reco.example" | ✅ | `tests/seo/test_no_placeholder_leak.test.ts` créé. Skip propre si `dist/` absent ; couvre `index.html`, toutes les pages HTML récursivement, et `robots.txt`. Le CI doit lancer `build` AVANT `test:seo`. |
| **L12 / P3-D** — Google Fonts doublon | ✅ | Inter retiré du `<link>` Google Fonts dans `Layout.astro` (Anton conservé). `@fontsource/inter` importé depuis `src/styles/global.css` (400/600/700). Self-host complet pour Inter → -1 round trip CDN, RGPD friendly. |
| **M21+** — cohabitation P2.13 / P2.14 | ✅ | Vérifié : skip-link, `lang={lang}`, `<noscript>`, `<SiteFooter>` (P2.14) cohabitent proprement avec `<MetaTags>` (P2.13). Aucun conflit. |

### Métriques de livraison (build 2026-06-11, `SITE_URL=https://source-internet.fr`)

| Métrique | Avant (P2.13) | Après (coordination finale) |
|----------|---------------|-----------------------------|
| OG cards générées | 106 | **3** (default + 1 source + 1 épisode sans YT) |
| Taille totale `/dist/og/` | ~8.4 MB | **~240 KB** (économie ≈ 8 MB) |
| Tests vitest SEO/OG | 63 | **66** (+3 placeholder leak) |
| JSON-LD home | ❌ absent | ✅ `WebSite` |
| JSON-LD source | ❌ absent | ✅ `PodcastSeries` + `BreadcrumbList` |
| JSON-LD épisode | ❌ absent | ✅ `PodcastEpisode` + N × `<recoType>` |
| `og:image` épisode | ✅ thumb YT | ✅ thumb YT (inchangé — priorité) |
| `og:image` source | ❌ default | ✅ carte Satori dédiée |
| Google Fonts CDN (Inter) | 1 link | **0** (self-host via fontsource) |
| `reco.example` dans `dist/` | n/a | **0** (vérifié par test) |

### Fichiers modifiés

- `src/layouts/Layout.astro` — retire Inter du `<link>` Google Fonts ;
  Anton conservé via `family=Anton` minimal.
- `src/styles/global.css` — `@import "@fontsource/inter/{400,600,700}.css"`.
- `src/pages/index.astro` — JSON-LD `WebSite` global.
- `src/pages/[source]/index.astro` — `ogSlug={source.id}` + JSON-LD
  (`PodcastSeries` + `BreadcrumbList`).
- `src/pages/[source]/episode/[guid].astro` — `ogSlug={source/episode/guid}`
  + JSON-LD (`PodcastEpisode` + recos non-citations).
- `src/pages/og/[...slug].png.ts` — `getStaticPaths` skip les épisodes
  avec YT thumb.
- `tests/seo/test_no_placeholder_leak.test.ts` — nouveau test post-build.

### Notes opérationnelles

- L'image OG d'un épisode reste la **miniature YouTube** quand elle existe
  (priorité dans `Layout.astro`). Le `ogSlug` posé sert uniquement de
  filet de sécurité (épisode sans YT → carte Satori dédiée).
- Le test `test_no_placeholder_leak.test.ts` est `skipIf(!distExists)` :
  en local sans build, il ne tourne pas → faux négatif évité. Le hook CI
  enchaîne `build` puis `test:seo`, ce qui active automatiquement le test.
- Anton (Google Fonts) reste en place car aucun package fontsource ne
  l'expose à ce jour. Quand un mirror fontsource d'Anton existera (ou
  qu'on l'embarquera nous-mêmes via `@font-face` + `src/fonts/`),
  on supprimera le dernier `<link>` Google Fonts.
