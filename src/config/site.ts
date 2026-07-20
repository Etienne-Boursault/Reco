/**
 * src/config/site.ts — Branding du site (par défaut Reco).
 *
 * Frontière de personnalisation pour les forks : un fork du kit qui veut
 * rebrander n'a qu'à modifier ce fichier (siteName, baseline, accent par
 * défaut, etc.). Tout le reste — template OG, MetaTags, footer — lit ces
 * constantes.
 *
 * Cf. ADR 0028 — Frontière de personnalisation pour forks.
 */

import { defaultTheme } from '../styles/tokens.js';

export interface SiteConfig {
  /** Nom du site, affiché dans `og:site_name` et le suffixe `<title>`. */
  siteName: string;
  /** Baseline / accroche courte (ex. footer, carte OG par défaut). */
  baseline: string;
  /** Domaine canonique (sans protocole) affiché dans la carte OG. */
  domainLabel: string;
  /** Couleur d'accent OG par défaut (override par theme de la source). */
  defaultAccent: string;
  /** Couleur de fond OG par défaut. */
  defaultBg: string;
  /** Couleur de texte OG par défaut. */
  defaultFg: string;
  /** Couleur muted OG par défaut. */
  defaultMuted: string;
  /** Email de contact pour le fallback signalement (P0-2). Si le POST
   *  `/api/report` est inopérant (pas d'adapter SSR), le ReportForm
   *  construit un `mailto:` vers cette adresse avec les champs saisis.
   *  Laisser `undefined` désactive le bouton fallback. */
  contactEmail?: string;
}

export const siteConfig: SiteConfig = {
  siteName: 'Reco',
  baseline: 'Catalogue de recommandations de podcasts',
  domainLabel: 'source-internet.fr',
  // Réutilise les tokens UI pour cohérence visuelle (cf. ADR 0030 + 0026).
  defaultAccent: defaultTheme.accent,
  defaultBg: defaultTheme.bg,
  defaultFg: defaultTheme.text,
  defaultMuted: defaultTheme.muted,
  // Optionnel : si défini, ReportForm propose un fallback "Envoyer par
  // email" quand le POST `/api/report` échoue (build static sans adapter).
  contactEmail: undefined,
};
