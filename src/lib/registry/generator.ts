/**
 * src/lib/registry/generator.ts — Construit un `RegistryDocument` à partir
 * des collections Astro d'un fork (sources/episodes/items/mentions).
 *
 * Le générateur est PUR : il ne touche pas au filesystem, il prend en entrée
 * des arrays légers et retourne le document JSON. Cela permet de :
 *   - tester sans monter Astro (vitest)
 *   - réutiliser le résultat dans l'endpoint `.well-known` ET dans une
 *     éventuelle commande CLI de validation.
 *
 * X-P0-32 (SSOT comptage) : les compteurs viennent de `computeGlobalCounts`
 * (stats), seule définition canonique. Le générateur ne (re)calcule jamais
 * itemsCount/mentionsCount/episodesCount/guestsCount localement.
 *
 * Cf. ADR 0045.
 */

import {
  REGISTRY_SCHEMA_VERSION,
  type RegistryDocument,
  type RegistryEndpoints,
} from './types.js';
import {
  computeGlobalCounts,
  type EpisodeLike,
  type ItemLike,
  type MentionLike,
  type SourceLike,
} from '../stats/aggregator.js';

/** Entrée minimale source (subset de la collection `sources`). */
export interface SourceInput {
  id: string;
  title: string;
  tagline?: string;
  hosts?: string[];
  rssUrl?: string;
  website?: string;
  /** Code langue (défaut `fr`). Lu depuis `source.data.lang` (ADR 0026). */
  language?: string;
  /** Date 1er épisode (YYYY-MM-DD), si connue. */
  since?: string;
}

export interface GeneratorInput {
  source: SourceInput;
  /** Épisodes du fork (avec date pour dériver `lastUpdatedAt`). */
  episodes: EpisodeLike[];
  /** Mentions (forme stats-like — recommendedBy, itemId, sourceRef, status). */
  mentions: MentionLike[];
  /** Items du catalogue (uniqueWorksCount = items mentionnés ∩ items). */
  items: ItemLike[];
  /** URL canonique du site (https://…) — ex. `import.meta.env.SITE` / `siteConfig`. */
  siteUrl: string;
  /** Version du générateur (ex. `Reco/0.3.0`). Lu depuis package.json. */
  generator: string;
  /** Date de génération (ISO 8601). Injecté pour la testabilité. */
  generatedAt: string;
  /**
   * Dernière modif des données (ISO 8601). Si absent, on dérive de
   * `max(episode.date)` (H24-3) — fallback `generatedAt` en dernier recours.
   */
  lastUpdatedAt?: string;
  /** URL du manifeste éthique du fork, si exposé. */
  manifestoUrl?: string;
  /**
   * Override des endpoints (R-P1-04). Pratique pour les forks qui exposent
   * des chemins custom (ex. CDN OG). Champs omis utilisent les défauts kit.
   */
  endpoints?: Partial<RegistryEndpoints>;
}

/**
 * Endpoints par défaut du kit Reco (F-N-8 : `as const` + `Object.freeze`
 * pour empêcher toute mutation accidentelle au runtime / dans les tests).
 */
const DEFAULT_ENDPOINTS = Object.freeze({
  ogImage: '/og/default.png',
  sitemap: '/sitemap-index.xml',
  search: '/search.json',
} as const satisfies RegistryEndpoints);

/**
 * ISO 8601 normalisé (utilisé pour `lastUpdatedAt` dérivé). Le schema
 * accepte les deux formats (avec/sans millisecondes) — on conserve la
 * sortie native de `Date.toISOString()` (F-L-10 : renommé `toIsoSeconds`
 * → `toIso`, le commentaire historique sur "seconde" était trompeur).
 */
function toIso(d: Date): string {
  return d.toISOString();
}

/** Calcule `lastUpdatedAt` à partir de `max(episode.date)` si possible. */
function deriveLastUpdatedAt(
  episodes: readonly EpisodeLike[],
  fallback: string,
): string {
  let max: Date | null = null;
  for (const e of episodes) {
    const raw = e.date;
    if (!raw) continue;
    const d = raw instanceof Date ? raw : new Date(raw);
    if (Number.isNaN(d.getTime())) continue;
    if (!max || d.getTime() > max.getTime()) max = d;
  }
  return max ? toIso(max) : fallback;
}

/**
 * Construit le document registry. Garantit que le résultat passera la
 * validation Zod (`parseRegistry`) tant que `siteUrl` est en https.
 *
 * Délègue le comptage à `computeGlobalCounts` (X-P0-32 SSOT).
 */
export function buildRegistry(input: GeneratorInput): RegistryDocument {
  const sourceLike: SourceLike = {
    id: input.source.id,
    hosts: input.source.hosts ?? [],
  };
  const counts = computeGlobalCounts({
    sources: [sourceLike],
    episodes: input.episodes,
    mentions: input.mentions,
    items: input.items,
  });

  const lastUpdatedAt =
    input.lastUpdatedAt ?? deriveLastUpdatedAt(input.episodes, input.generatedAt);

  const endpoints: RegistryEndpoints = {
    ...DEFAULT_ENDPOINTS,
    ...(input.endpoints ?? {}),
  };

  // F-CRIT-8 : normalise `language` (BCP-47 `fr-FR`, `en_US`, espace en
  // trop, etc.) vers le code ISO 639-1 2 lettres minuscules attendu par
  // le schema (`/^[a-z]{2}$/`). Fallback `fr` si rien d'utilisable.
  const rawLang = (input.source.language ?? '').trim().toLowerCase();
  const normalizedLang = /^[a-z]{2}/.test(rawLang) ? rawLang.slice(0, 2) : 'fr';

  const doc: RegistryDocument = {
    schemaVersion: REGISTRY_SCHEMA_VERSION,
    siteUrl: input.siteUrl,
    podcast: {
      title: input.source.title,
      tagline: input.source.tagline,
      rssUrl: input.source.rssUrl,
      hosts: [...(input.source.hosts ?? [])],
      since: input.source.since,
      language: normalizedLang,
    },
    stats: {
      itemsCount: counts.uniqueWorksCount,
      mentionsCount: counts.recommendationsCount,
      episodesCount: counts.episodesCount,
      guestsCount: counts.uniqueGuestsCount,
      lastUpdatedAt,
    },
    meta: {
      generator: input.generator,
      generatedAt: input.generatedAt,
      manifesto: input.manifestoUrl,
    },
    endpoints,
  };
  return doc;
}
