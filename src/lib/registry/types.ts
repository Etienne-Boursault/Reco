/**
 * src/lib/registry/types.ts — Schema du registry public Reco.
 *
 * Chaque fork du kit expose `/.well-known/reco-registry.json` — un document
 * machine-readable qui permet à des méta-agrégateurs (ex. source-internet.fr)
 * de découvrir le podcast, ses stats, et son endpoint OG/sitemap.
 *
 * Le schema est versionné (`schemaVersion: 1`). Toute évolution non rétro-
 * compatible DOIT bumper le numéro et lister les changements dans ADR 0045.
 *
 * SSOT : ce fichier est la frontière. Le générateur (`generator.ts`) écrit
 * le JSON, le consumer (`consumer.ts`) le lit + valide.
 *
 * Mode strict (H24-2) : tous les objets utilisent `.strict()` — un champ
 * inattendu est rejeté. Cela protège contre les évolutions silencieuses
 * (typo, extension non documentée).
 */

import { z } from 'astro/zod';

/** Version courante du schema. */
export const REGISTRY_SCHEMA_VERSION = 1 as const;

/**
 * ISO 8601 date-time (UTC ou offset) — regex stricte (L24-21).
 *
 * Limites volontaires (F-M-11) :
 *   - calendrier : on accepte `MM=01-12` mais on ne valide PAS que
 *     `DD` est valide pour le mois (ex. `2026-02-31T00:00:00Z` passe).
 *     Le `new Date(...)` consumer-side filtrera, on évite la regex
 *     monstrueuse.
 *   - heures 00-23, minutes/secondes 00-59 (rejette `T07:45:60Z`).
 *   - on accepte les fractions de seconde (`.123` ou `.123456`) et
 *     l'offset `Z`/`±HH:MM` (mais PAS `±HHMM` sans deux-points — la
 *     RFC 3339 l'accepte, on choisit la forme stricte pour cohérence
 *     interop avec les agrégateurs).
 *   - pas de validation des secondes intercalaires (`23:59:60`).
 */
const isoDateTime = z
  .string()
  .regex(
    /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/,
    'ISO 8601 date-time attendu (ex. 2026-06-12T07:45:00Z)',
  );

/** ISO 639-1 — code langue 2 lettres. */
const lang = z.string().regex(/^[a-z]{2}$/, 'Code langue ISO 639-1 attendu');

/**
 * URL HTTPS absolue (pas de http en clair pour les méta-cards).
 *
 * F-H-8 : on tolère `http://` quand `NODE_ENV !== 'production'` pour
 * permettre les tests locaux contre un dev server (`http://localhost:4321`)
 * sans monter de cert TLS — la production reste protégée.
 */
/** Lu à chaque validation pour que les tests puissent flipper la valeur. */
function httpAllowed(): boolean {
  return process.env.NODE_ENV !== 'production';
}
const httpsUrl = z.string().url().refine(
  (u) => u.startsWith('https://') || (httpAllowed() && u.startsWith('http://')),
  'URL HTTPS attendue',
);

/**
 * Chemin relatif (`/...`) ou URL absolue HTTPS (M24-7). Couvre les endpoints
 * OG/sitemap/search exposés par le fork.
 */
const pathOrHttpsUrl = z
  .string()
  .regex(
    /^\/[\w./\-?=&%~+:#]*$|^https:\/\/[\w./\-?=&%~+:#@!]+$/,
    'Chemin absolu (/...) ou URL HTTPS attendu',
  );

/** Bornes raisonnables — DoS / pollution (M24-5, M24-6). */
export const REGISTRY_LIMITS = {
  titleMax: 200,
  taglineMax: 500,
  hostMax: 200,
  hostsMax: 64,
  generatorMax: 100,
} as const;

export const registryPodcastSchema = z
  .object({
    title: z.string().min(1).max(REGISTRY_LIMITS.titleMax),
    tagline: z.string().max(REGISTRY_LIMITS.taglineMax).optional(),
    rssUrl: z.string().url().optional(),
    hosts: z
      .array(z.string().min(1).max(REGISTRY_LIMITS.hostMax))
      .max(REGISTRY_LIMITS.hostsMax)
      .default([]),
    since: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'YYYY-MM-DD').optional(),
    language: lang,
  })
  .strict();

export const registryStatsSchema = z
  .object({
    itemsCount: z.number().int().min(0),
    mentionsCount: z.number().int().min(0),
    episodesCount: z.number().int().min(0),
    guestsCount: z.number().int().min(0),
    lastUpdatedAt: isoDateTime,
  })
  .strict();

export const registryMetaSchema = z
  .object({
    generator: z.string().min(1).max(REGISTRY_LIMITS.generatorMax),
    generatedAt: isoDateTime,
    manifesto: z.string().url().optional(),
  })
  .strict();

export const registryEndpointsSchema = z
  .object({
    ogImage: pathOrHttpsUrl.optional(),
    sitemap: pathOrHttpsUrl.optional(),
    search: pathOrHttpsUrl.optional(),
  })
  .strict();

/**
 * Document principal — strict.
 *
 * Champ réservé `podcasts` (R-P1-05) : permettra à un fork multi-source de
 * publier un array d'entrées sans bumper le `schemaVersion`. Phase 4.5.
 * Reste optionnel et non lu par le consumer en v1.
 */
export const registryDocumentSchema = z
  .object({
    schemaVersion: z.literal(REGISTRY_SCHEMA_VERSION),
    siteUrl: httpsUrl,
    podcast: registryPodcastSchema,
    podcasts: z.array(registryPodcastSchema).optional(),
    stats: registryStatsSchema,
    meta: registryMetaSchema,
    endpoints: registryEndpointsSchema.default({}),
  })
  .strict();

export type RegistryPodcast = z.infer<typeof registryPodcastSchema>;
export type RegistryStats = z.infer<typeof registryStatsSchema>;
export type RegistryMeta = z.infer<typeof registryMetaSchema>;
export type RegistryEndpoints = z.infer<typeof registryEndpointsSchema>;
export type RegistryDocument = z.infer<typeof registryDocumentSchema>;

/**
 * Schema d'une entrée du meta-index agrégé (1 registry + son URL d'origine).
 *
 * F-N-5 : le type `RegistryEntry` est dérivé via `z.infer` plutôt que
 * dupliqué en `interface` — garantit qu'il reste aligné avec le schema si
 * on ajoute des champs (slug computed, source-of-truth unique).
 */
export const registryEntrySchema = z
  .object({
    /** URL absolue où le registry a été fetché. */
    sourceUrl: z.string(),
    /** Slug stable dérivé du siteUrl (host sans port, lowercase). */
    slug: z.string(),
    /** Document validé. */
    registry: registryDocumentSchema,
  })
  .strict();
export type RegistryEntry = z.infer<typeof registryEntrySchema>;

/**
 * Parse + valide un registry brut (JSON). Lève une `ZodError` en cas d'échec.
 * Convention : on RETOURNE l'instance validée (avec defaults appliqués).
 */
export function parseRegistry(raw: unknown): RegistryDocument {
  return registryDocumentSchema.parse(raw);
}

/** Variante safe : ne lève pas, retourne `null` + une raison en cas d'échec. */
export function tryParseRegistry(
  raw: unknown,
): { ok: true; value: RegistryDocument } | { ok: false; error: string } {
  const result = registryDocumentSchema.safeParse(raw);
  if (result.success) return { ok: true, value: result.data };
  return { ok: false, error: result.error.issues.map((i) => i.message).join('; ') };
}

/**
 * Protocole formel (R-P1-02) — toute source qui produit un `RegistryDocument`
 * implémente cette interface. Utilisé par les forks qui veulent injecter un
 * loader custom (cache HTTP, signature, etc.).
 */
export interface MetaIndexLoader {
  load(): {
    entries: RegistryEntry[];
    totals: {
      podcasts: number;
      items: number;
      mentions: number;
      episodes: number;
      guests: number;
    };
    generatedAt?: string;
  } | null;
}
