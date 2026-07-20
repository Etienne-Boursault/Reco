/**
 * src/lib/theme/tokens.ts — Réexport des tokens partagés UI ↔ OG.
 *
 * SSOT effective : `src/styles/tokens.ts` (créé par Fixer P2.14 / ADR 0030).
 * Ce module sert d'indirection stable pour les consommateurs OG/SEO :
 *  - `src/lib/og/template.ts`  → applique `defaultTheme` au rendu PNG
 *  - `src/config/site.ts`      → couleurs OG par défaut
 *  - `src/components/MetaTags.astro` → `themeColor` mobile
 *
 * Cf. ADR 0030 — Design tokens & theming multi-source (SSOT UI).
 *     ADR 0026 — Tokens de thème partagés (étend l'usage à OG/SEO).
 */

export {
  defaultTheme,
  contrastCases,
  type ThemeColors,
  type ContrastCase,
} from '../../styles/tokens.js';
