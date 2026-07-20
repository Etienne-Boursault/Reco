/**
 * src/lib/tracking/settings.ts — Settings de tracking par source
 * (pattern Phase 3.5 audit_core, cf. R-P1-13).
 *
 * Permet de surcharger window/maxHits/category-mapping par source via
 * `extra.tracking` dans le registry. Si absent → defaults raisonnables.
 *
 * Aussi expose `categorizeUrl(href)` (R-P1-16, L25-27) : helper centralisé
 * pour mapper une URL externe vers une `ClickCategory`. Réutilisé par
 * `OutboundLink.astro` (category optionnelle → auto-déduite).
 */

import type { ClickCategory } from './types.js';
import { CLICK_CATEGORIES } from './types.js';

export interface TrackingSettings {
  /** Fenêtre rate-limit en millisecondes. */
  readonly windowMs: number;
  /** Hits max dans la fenêtre. */
  readonly maxHits: number;
  /**
   * Overrides hostname → category. Fusionné avec le mapping par défaut
   * (les overrides écrasent).
   */
  readonly categoryOverrides: Readonly<Record<string, ClickCategory>>;
}

const DEFAULT_WINDOW_MS = 60_000;
const DEFAULT_MAX_HITS = 60;

export const DEFAULT_TRACKING_SETTINGS: TrackingSettings = Object.freeze({
  windowMs: DEFAULT_WINDOW_MS,
  maxHits: DEFAULT_MAX_HITS,
  categoryOverrides: Object.freeze({}),
});

function isClickCategory(value: unknown): value is ClickCategory {
  return typeof value === 'string' && (CLICK_CATEGORIES as readonly string[]).includes(value);
}

/**
 * Construit `TrackingSettings` à partir du champ `extra.tracking` d'une
 * source du registry. Tolère les champs manquants / mal typés (fallback
 * defaults — never throws sur input invalide).
 *
 * Forme attendue :
 *   extra.tracking = {
 *     windowMs?: number,
 *     maxHits?: number,
 *     categoryOverrides?: { "host.example": "tmdb", ... }
 *   }
 */
export function fromSourceExtra(extra: unknown): TrackingSettings {
  if (!extra || typeof extra !== 'object') return DEFAULT_TRACKING_SETTINGS;
  const root = (extra as Record<string, unknown>).tracking;
  if (!root || typeof root !== 'object') return DEFAULT_TRACKING_SETTINGS;
  const cfg = root as Record<string, unknown>;

  const windowMs =
    typeof cfg.windowMs === 'number' && Number.isFinite(cfg.windowMs) && cfg.windowMs > 0
      ? cfg.windowMs
      : DEFAULT_WINDOW_MS;
  const maxHits =
    typeof cfg.maxHits === 'number' && Number.isFinite(cfg.maxHits) && cfg.maxHits > 0
      ? Math.floor(cfg.maxHits)
      : DEFAULT_MAX_HITS;

  const rawOverrides = cfg.categoryOverrides;
  const overrides: Record<string, ClickCategory> = {};
  if (rawOverrides && typeof rawOverrides === 'object') {
    for (const [host, cat] of Object.entries(rawOverrides as Record<string, unknown>)) {
      if (typeof host !== 'string' || !host) continue;
      if (!isClickCategory(cat)) {
        // B-LOW-18 : observabilité debug — une catégorie inconnue dans le
        // registry est très probablement une typo (ex: "Spotify" vs "spotify").
        if (process.env.RECO_QUIET !== '1') {
          // eslint-disable-next-line no-console
          console.warn(
            `[tracking/settings] categoryOverrides["${host}"] = ${JSON.stringify(cat)} ignoré (catégorie inconnue).`,
          );
        }
        continue;
      }
      overrides[host.toLowerCase()] = cat;
    }
  }

  return Object.freeze({
    windowMs,
    maxHits,
    categoryOverrides: Object.freeze(overrides),
  });
}

/**
 * Default category mapping (R-P1-16, L25-27). Matche par hostname
 * (endsWith) pour couvrir sous-domaines (`www.imdb.com`, etc.).
 * Liste ordonnée : on stop au premier match.
 */
const DEFAULT_HOST_MAP: ReadonlyArray<readonly [string, ClickCategory]> = Object.freeze([
  ['themoviedb.org', 'tmdb'],
  ['tmdb.org', 'tmdb'],
  ['spotify.com', 'spotify'],
  ['imdb.com', 'imdb'],
  ['youtube.com', 'youtube'],
  ['youtu.be', 'youtube'],
  ['placedeslibraires.fr', 'library'],
  ['lalibrairie.com', 'library'],
  ['leslibraires.fr', 'library'],
  ['bookshop.org', 'library'],
  ['librairie', 'library'], // fallback substring final
] as const);

/**
 * Mappe une URL externe vers une `ClickCategory`. Stratégie :
 *  1. on parse l'URL — fail-safe `'other'` si invalide,
 *  2. on cherche dans `overrides` (settings.categoryOverrides),
 *  3. puis dans le mapping par défaut.
 */
export function categorizeUrl(
  href: string,
  overrides: Readonly<Record<string, ClickCategory>> = {},
): ClickCategory {
  let host: string;
  try {
    host = new URL(href).hostname.toLowerCase();
  } catch {
    return 'other';
  }
  if (!host) return 'other';
  // Overrides : match exact host OU endsWith(`.${host}`)
  for (const [key, cat] of Object.entries(overrides)) {
    if (host === key || host.endsWith(`.${key}`)) return cat;
  }
  for (const [needle, cat] of DEFAULT_HOST_MAP) {
    if (host === needle || host.endsWith(`.${needle}`)) return cat;
    if (needle === 'librairie' && host.includes(needle)) return cat;
  }
  return 'other';
}

export const TrackingSettings = Object.freeze({
  fromSourceExtra,
  DEFAULTS: DEFAULT_TRACKING_SETTINGS,
});
