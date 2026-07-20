/**
 * src/styles/tokens.ts — Design tokens (palette par défaut).
 *
 * SSOT (single source of truth) pour la palette du thème par défaut. Importé
 * par :
 *   - `tests/a11y/check_contrast.mjs` : valide les ratios WCAG AA sur la
 *     palette par défaut et sur chaque thème de source découvert.
 *   - (future) génération de variables CSS build-time si besoin.
 *
 * Les couleurs CSS dans `src/styles/global.css` doivent rester en cohérence
 * avec ces valeurs (la couleur effective est ensuite surchargée par source
 * via Layout.astro `style="--bg:...;"` injecté en SSR).
 *
 * Cf. ADR 0024 — Design tokens & theming multi-source.
 */

export interface ThemeColors {
  bg: string;
  surface: string;
  text: string;
  muted: string;
  accent: string;
  accentText: string;
}

/** Palette par défaut (mode sombre, valeurs cohérentes avec global.css). */
export const defaultTheme: ThemeColors = {
  bg: '#0e0e10',
  surface: '#17171c',
  text: '#f6f4ee',
  muted: '#9a99a3',
  accent: '#ffd23f',
  accentText: '#0e0e10',
};

/** Cas de contraste WCAG AA contrôlés par le check. */
export interface ContrastCase {
  /** Libellé lisible (apparaît dans le rapport). */
  name: string;
  /** Couleur du premier plan (clé de ThemeColors). */
  fg: keyof ThemeColors;
  /** Couleur du fond (clé de ThemeColors). */
  bg: keyof ThemeColors;
  /** Ratio minimum (4.5 pour texte normal, 3 pour non-textuel / large text). */
  min: number;
}

/**
 * Cas couverts par le check contraste. À étendre avec parcimonie : chaque
 * cas correspond à une combinaison réellement utilisée dans le CSS.
 */
export const contrastCases: ContrastCase[] = [
  { name: 'texte / bg (corps)', fg: 'text', bg: 'bg', min: 4.5 },
  { name: 'texte / surface (cartes)', fg: 'text', bg: 'surface', min: 4.5 },
  { name: 'muted / bg (info secondaire)', fg: 'muted', bg: 'bg', min: 4.5 },
  { name: 'accent / bg (emphase, badges)', fg: 'accent', bg: 'bg', min: 4.5 },
  { name: 'accent / surface (badges sur carte)', fg: 'accent', bg: 'surface', min: 4.5 },
  { name: 'accentText / accent (CTA)', fg: 'accentText', bg: 'accent', min: 4.5 },
  // Tab inactif : on utilise text avec opacity 78%. Approx : on test text/bg.
  { name: 'tab inactif (text 78% / bg)', fg: 'text', bg: 'bg', min: 4.5 },
  // Focus ring : non-textuel, WCAG 1.4.11 → seuil 3:1.
  { name: 'focus ring (accent / bg)', fg: 'accent', bg: 'bg', min: 3 },
  { name: 'focus ring (accent / surface)', fg: 'accent', bg: 'surface', min: 3 },
];
