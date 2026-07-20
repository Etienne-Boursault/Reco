/**
 * src/lib/stats/types.ts — Types & schémas Zod pour les stats publiques.
 *
 * Ces types décrivent le snapshot `stats.json` produit build-time par
 * `tools/build_stats.py` ainsi que les structures internes consommées par
 * les pages `/stats` et `/[source]/stats`.
 *
 * Cf. ADR 0047 (stats publiques globales).
 *
 * Issues fixées : H26-1 (`.strict()` partout — interdit les clés inconnues
 * silencieuses qui maskeraient une dérive de schéma), M26-5 (ISO 8601
 * strict pour `generatedAt`).
 */
import { z } from 'zod';

/** Version courante du schema `stats.json`. Bump si breaking change. */
export const STATS_SCHEMA_VERSION = 1 as const;

/**
 * Regex ISO 8601 stricte — `YYYY-MM-DDTHH:MM:SS[.sss]Z` (UTC). On accepte
 * une partie fractionnaire optionnelle (`.123`) pour la compat Node /
 * Python (Python `strftime("%Y-%m-%dT%H:%M:%SZ")` ; Node
 * `Date.prototype.toISOString` ajoute `.sssZ`).
 */
const ISO_UTC_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/;

// --- Sous-schemas -----------------------------------------------------------

export const globalCountsSchema = z
  .object({
    podcastsCount: z.number().int().min(0),
    episodesCount: z.number().int().min(0),
    recommendationsCount: z.number().int().min(0),
    uniqueWorksCount: z.number().int().min(0),
    uniqueGuestsCount: z.number().int().min(0),
  })
  .strict();

export const topGuestSchema = z
  .object({
    name: z.string().min(1),
    slug: z.string().min(1),
    count: z.number().int().min(0),
  })
  .strict();

export const topWorkSchema = z
  .object({
    id: z.string().min(1),
    title: z.string().min(1),
    type: z.string().min(1),
    mentionsCount: z.number().int().min(0),
  })
  .strict();

export const monthlyBucketSchema = z
  .object({
    /** Mois ISO `YYYY-MM`. */
    month: z.string().regex(/^\d{4}-\d{2}$/),
    count: z.number().int().min(0),
  })
  .strict();

export const statsSnapshotSchema = z
  .object({
    schemaVersion: z.literal(STATS_SCHEMA_VERSION),
    generatedAt: z.string().regex(ISO_UTC_RE, 'ISO 8601 UTC requis (`YYYY-MM-DDTHH:MM:SSZ`)'),
    global: globalCountsSchema,
    perSource: z.record(z.string(), globalCountsSchema),
    topGuests: z.array(topGuestSchema),
    topWorks: z.array(topWorkSchema),
    typeDistribution: z.record(z.string(), z.number().int().min(0)),
    monthlyEpisodes: z.array(monthlyBucketSchema),
  })
  .strict();

// --- Types dérivés ----------------------------------------------------------

export type GlobalCounts = z.infer<typeof globalCountsSchema>;
export type TopGuest = z.infer<typeof topGuestSchema>;
export type TopWork = z.infer<typeof topWorkSchema>;
export type MonthlyBucket = z.infer<typeof monthlyBucketSchema>;
export type StatsSnapshot = z.infer<typeof statsSnapshotSchema>;
