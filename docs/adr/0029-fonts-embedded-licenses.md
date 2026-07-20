# ADR 0029 — Polices embarquées : licences & taille de bundle

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco
- ADRs liés : ADR 0021 (SEO/OG)

## Contexte

ADR 0021 chargeait Inter (régulier 400 + bold 700) depuis
`node_modules/@fontsource/inter/files/` — un package de **200+ fichiers
WOFF/WOFF2** (toutes graisses, latin-ext, cyrillic, vietnamese…) dont
le renderer OG n'utilisait que **2** : `inter-latin-400-normal.woff` et
`inter-latin-700-normal.woff`.

Conséquences :
- 8 MB+ inutiles dans `node_modules` pour 168 KB effectivement lus.
- Dépendance runtime à un package npm pour un asset stable.
- Si `@fontsource/inter` change la convention de nommage des fichiers
  (déjà arrivé en v5), le renderer casse silencieusement (fallback
  Satori = tofu).

## Décision

1. Commit explicite des deux WOFF dans `src/fonts/og/` :
   - `inter-latin-400-normal.woff` (≈ 84 KB)
   - `inter-latin-700-normal.woff` (≈ 84 KB)
2. Mention licence : **Inter — SIL Open Font License 1.1**, copyright
   Rasmus Andersson. Fichier `NOTICE` à la racine du repo (ou
   `src/fonts/og/LICENSE`) reproduit le texte OFL.
3. `@fontsource/inter` reste en `devDependencies` comme **fallback** du
   loader (pratique pour `npm i` sans copier la police à la main) mais
   n'est plus une dépendance runtime du build.
4. Migration éventuelle vers WOFF2 (compression ~30 % en plus) repoussée :
   gain marginal sur 168 KB embarqués au build.

## Conséquences

- Bundle déterministe — `git clone && npm i && npm run build` produit
  le même OG, même si le registry npm a changé entre-temps.
- Risque licence couvert (OFL 1.1 autorise la redistribution avec
  attribution, qui est posée dans NOTICE).
- Onboarding fork : la police « marche » sans étape supplémentaire.

## Action

Les fichiers WOFF doivent être copiés manuellement (`cp
node_modules/@fontsource/inter/files/inter-latin-{400,700}-normal.woff
src/fonts/og/`) lors de la mise en place — le repo commit l'asset
binaire après cette étape.

## Coordination — Anton retiré 2026-06-11

- **Constat (Fixer final Phase 2, P0-4)** : `Layout.astro` chargeait
  Anton depuis `fonts.googleapis.com` (preconnect googleapis + gstatic
  + lien CSS). Conséquence : l'IP de chaque visiteur fuit vers Google
  côté CDN, ce qui contredit le positionnement « no tracker tiers »
  d'ADR 0034 §positives et plus largement la promesse RGPD du kit.
- **Décision** : Option B retenue — Anton est retiré de la palette.
  Inter (self-hosté via `@fontsource/inter`) est utilisé pour body
  ET heading (variable `--font-display` repointée sur Inter dans
  `src/styles/global.css`).
- **Pourquoi pas l'Option A (Anton self-hosté en WOFF2)** : licence
  OFL à pister, +50 KB minimum bundle, surface CSP en plus, pour un
  gain visuel marginal (heading display rarement vu sur > 95 % du
  trafic). Inter en `font-weight: 700` rend très bien sur les
  titres.
- **Migration fork** : aucune action — un fork qui veut Anton peut
  re-ajouter `@font-face` en self-host dans `global.css` et copier
  le WOFF2 depuis `https://fonts.gstatic.com/s/anton/v25/1Ptgg87LROyAm0K08i4gS7lu.woff2`
  (OFL 1.1, attribution nécessaire dans `NOTICE`).

## Coordination — Bebas Neue réintroduite 2026-06-12

- **Constat** : Inter en 700 sur les h1/h2/h3 perdait l'identité
  « presse condensée » initialement voulue avec Anton. Besoin d'une
  alternative libre proche d'Anton sans réintroduire Google Fonts.
- **Décision** : **Bebas Neue** retenue (SIL Open Font License 1.1,
  self-hostée via `@fontsource/bebas-neue` — même pattern qu'Inter).
  Variable `--font-display` passe à `'Bebas Neue', 'Inter', system-ui,
  sans-serif` (fallback chain en cascade si la font ne charge pas).
- **Alternatives écartées** :
  - Fjalla One (proche d'Anton mais moins reconnue, fallback chain
    moins évidente).
  - Oswald (multi-weight, mais identité moins percutante).
  - Barlow Condensed (trop discret pour de l'éditorial).
- **Coût** : +1 WOFF2 latin 400 (~15 KB), 1 import CSS supplémentaire.
  Pas de surface CSP nouvelle (toujours self-hostée, pas de domaine
  tiers).
- **Migration fork** : aucune action — `@fontsource/bebas-neue` est en
  `devDependencies` ; un fork qui préfère son propre look display
  édite `--font-display` dans son `theme.colors.css` (cf. ADR 0030).
- **Polices de série propriétaires (ex. font de Bref)** : si une font
  propriétaire est validée pour usage perso d'un fork (sans droit de
  redistribution), poser le WOFF2 dans `public/fonts/<slug>/` +
  ajouter à `.gitignore` puis déclarer un `@font-face` dans le CSS
  de surcharge du fork. NE PAS commiter le binaire dans le repo
  upstream MIT.
