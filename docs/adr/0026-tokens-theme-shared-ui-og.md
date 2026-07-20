# ADR 0026 — Tokens de thème partagés (UI + OG)

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco
- ADRs liés : ADR 0030 (design tokens SSOT), ADR 0021 (SEO/OG), ADR 0022 (a11y AA)

## Contexte

ADR 0030 a posé `src/styles/tokens.ts` comme SSOT couleurs UI (`bg`,
`accent`, `text`, `muted`, `surface`, `accentText`) avec un check
contraste WCAG AA (`tests/a11y/check_contrast.mjs`).

P2.13 (ADR 0021) a livré des OG cards build-time dont le template
hardcodait sa propre palette (`#5eead4` accent, `#0e0e10` bg, etc.).
Conséquence : si une source change son `accent` via `theme.colors.accent`
dans son JSON, l'UI suit, l'OG suit aussi, **mais les défauts** quand
aucune source n'est branchée (homepage, page catalogue) divergeaient.
Plus grave : aucun test WCAG ne couvrait les couples OG (`fg/bg`
sur la carte PNG).

## Décision

1. Le template OG (`src/lib/og/template.ts`) ne hardcode plus de couleur.
   Il importe ses défauts depuis `src/config/site.ts`, qui lui-même
   réexporte `defaultTheme` de `src/styles/tokens.ts`. Un seul point de
   modification, deux consommateurs (UI + PNG).
2. Un fichier d'indirection `src/lib/theme/tokens.ts` réexporte les
   symboles : permet aux futurs consommateurs OG d'importer depuis un
   chemin neutre sans dépendre de `src/styles/` (qui pourrait évoluer).
3. Le check contraste `tests/a11y/check_contrast.mjs` couvre déjà les
   couples critiques (`text/bg`, `accent/bg`, `accent/surface`). Les
   couples OG (`fg/bg`, `accent/bg` sur la carte) sont identiques aux
   couples UI puisqu'ils partagent la palette — pas de nouveau cas
   nécessaire, sauf si une source override accent OG seul (non prévu).

## Alternatives écartées

- Dupliquer la palette dans `template.ts` : casse SSOT (déjà la
  source du bug initial).
- Importer directement `src/styles/tokens.ts` depuis le template : crée
  un couplage `og` → `styles` peu lisible ; l'indirection `lib/theme/`
  documente l'intention.

## Conséquences

- Un fork qui rebrande change `src/config/site.ts` (siteName, baseline)
  et `src/styles/tokens.ts` (palette) — c'est tout.
- Le gradient fin de la carte OG est calculé dynamiquement (`lighten()`
  de 6 % vers blanc) à partir de la couleur `bg`, donc cohérent quel
  que soit le thème (plus de hardcode `#1a1a1f` qui clashait avec
  un thème clair).
