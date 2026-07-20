/**
 * src/lib/stats/page.ts — Helpers JSON-LD pour la page `/stats`.
 *
 * Émet un `schema.org/Dataset` pointant vers `stats.json` (URL publique
 * via Astro.site). Cf. ADR 0047.
 *
 * Issues fixées :
 *  - M26-16 : enrichi `keywords`, `license`, `publisher`, `temporalCoverage`.
 *  - M26-17 : `distribution[DataDownload]` exposé via `/stats.json` (cf.
 *    endpoint `src/pages/stats.json.ts`).
 *  - M26-18 : `publisher` paramétrable depuis `siteConfig` (ADR 0028).
 */
import type { StatsSnapshot, MonthlyBucket } from './types';
import type {
  EpisodeLike,
  ItemLike,
  MentionLike,
  SourceLike,
} from './aggregator';
import { buildStatsSnapshot } from './aggregator';

export interface StatsPublisher {
  name: string;
  url?: string;
}

export interface StatsDatasetSchemaArgs {
  /** URL canonique absolue de la page `/stats`. */
  pageUrl: string;
  /** URL absolue du fichier `stats.json` téléchargeable (optionnel). */
  distributionUrl?: string;
  name: string;
  description: string;
  /** Snapshot — fournit `generatedAt` + counts + monthly pour couverture temporelle. */
  snapshot: Pick<StatsSnapshot, 'generatedAt' | 'global'> & {
    monthlyEpisodes?: readonly MonthlyBucket[];
  };
  /** Publisher (fallback `Reco`, paramétrable via `siteConfig`). */
  publisher?: StatsPublisher;
  /** Mots-clés thématiques pour le moteur de recherche. */
  keywords?: readonly string[];
  /**
   * Licence SPDX/URL — défaut `MIT` (cohérent avec le kit open-source).
   * Accepte une URL custom pour les forks sous licence différente.
   */
  license?: string;
}

const DEFAULT_KEYWORDS = [
  'podcast',
  'recommandations',
  'statistiques',
  'culture',
  'open data',
] as const;
const DEFAULT_LICENSE = 'https://opensource.org/licenses/MIT';

/**
 * Construit l'intervalle ISO 8601 « temporalCoverage » à partir des
 * monthly buckets (premier → dernier mois). Format `YYYY-MM/YYYY-MM`
 * (cf. schema.org/temporalCoverage qui suit l'intervalle ISO 8601).
 */
function buildTemporalCoverage(
  monthly: readonly MonthlyBucket[] | undefined,
): string | undefined {
  if (!monthly || monthly.length === 0) return undefined;
  const first = monthly[0].month;
  const last = monthly[monthly.length - 1].month;
  return first === last ? first : `${first}/${last}`;
}

/** Construit le bloc JSON-LD `Dataset` schema.org pour la page stats. */
export function statsDatasetSchema(
  args: StatsDatasetSchemaArgs,
): Record<string, unknown> {
  const publisher = args.publisher ?? { name: 'Reco' };
  const publisherNode: Record<string, unknown> = {
    '@type': 'Organization',
    name: publisher.name,
  };
  if (publisher.url) publisherNode.url = publisher.url;

  const node: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Dataset',
    name: args.name,
    description: args.description,
    url: args.pageUrl,
    dateModified: args.snapshot.generatedAt,
    inLanguage: 'fr',
    keywords: [...(args.keywords ?? DEFAULT_KEYWORDS)],
    license: args.license ?? DEFAULT_LICENSE,
    creator: publisherNode,
    publisher: publisherNode,
    // F-M-13 — itère `Object.entries(global)` plutôt que de lister chaque
    // clé : zéro maintenance si un nouveau compteur est ajouté à
    // `globalCountsSchema`. L'ordre des clés du snapshot fait foi (ADR 0047).
    variableMeasured: Object.entries(args.snapshot.global).map(
      ([name, value]) => ({ '@type': 'PropertyValue', name, value }),
    ),
  };
  const temporalCoverage = buildTemporalCoverage(args.snapshot.monthlyEpisodes);
  if (temporalCoverage) node.temporalCoverage = temporalCoverage;
  if (args.distributionUrl) {
    node.distribution = [
      {
        '@type': 'DataDownload',
        encodingFormat: 'application/json',
        contentUrl: args.distributionUrl,
      },
    ];
  }
  return node;
}

// --- Helper page (F-H-6) ----------------------------------------------------

export interface LoadStatsForPageArgs {
  /** Filtre source ; absent → page globale `/stats`. */
  sourceId?: string;
  /** Snapshot pré-calculé (sidecar `tools/output/stats/.../stats.json`). */
  sidecar?: StatsSnapshot | null;
  /** Collections déjà extraites & projetées en formes minimales. */
  collections: {
    sources: readonly SourceLike[];
    episodes: readonly EpisodeLike[];
    mentions: readonly MentionLike[];
    items: readonly ItemLike[];
  };
  pageUrl: string;
  distributionUrl?: string;
  datasetName: string;
  datasetDescription: string;
  publisher?: StatsPublisher;
  /** Locale pour `generatedLocal` — `'fr-FR'` par défaut. */
  locale?: string;
  /** Top N affiché (cards). Défaut 10 — cohérent ADR 0047. */
  topListLimit?: number;
}

export interface StatsRow {
  label: string;
  count: number;
  sub?: string;
}

export interface StatsBar {
  label: string;
  value: number;
}

export interface LoadStatsForPageResult {
  snapshot: StatsSnapshot;
  generatedLocal: string;
  topGuests: StatsRow[];
  topWorks: StatsRow[];
  distributionBars: StatsBar[];
  monthlyBars: StatsBar[];
  jsonLd: Record<string, unknown>;
}

/**
 * Helper « thin page » : prend les collections + sidecar optionnel, calcule
 * le snapshot (si sidecar absent), dérive les view-models pour les
 * composants `StatCard` / `TopList` / `StatChart`, et émet le JSON-LD.
 *
 * F-H-6 : `stats.astro` et `[source]/stats.astro` deviennent quasi
 * identiques (DRY). Le helper est pur (pas d'I/O fs, pas de `getCollection`)
 * pour être testable en unitaire — les pages Astro injectent les
 * collections déjà extraites.
 */
export function loadStatsForPage(
  args: LoadStatsForPageArgs,
): LoadStatsForPageResult {
  const snapshot =
    args.sidecar ??
    buildStatsSnapshot({
      sources: args.collections.sources,
      episodes: args.collections.episodes,
      mentions: args.collections.mentions,
      items: args.collections.items,
      options: args.sourceId ? { sourceId: args.sourceId } : undefined,
    });

  const limit = args.topListLimit ?? 10;
  const topGuests: StatsRow[] = snapshot.topGuests
    .slice(0, limit)
    .map((g) => ({ label: g.name, count: g.count }));
  const topWorks: StatsRow[] = snapshot.topWorks
    .slice(0, limit)
    .map((w) => ({ label: w.title, count: w.mentionsCount, sub: w.type }));
  const distributionBars: StatsBar[] = Object.entries(
    snapshot.typeDistribution,
  ).map(([label, value]) => ({ label, value }));
  const monthlyBars: StatsBar[] = snapshot.monthlyEpisodes.map((m) => ({
    label: m.month,
    value: m.count,
  }));

  const generatedLocal = formatGeneratedAt(snapshot.generatedAt, args.locale);

  const jsonLd = statsDatasetSchema({
    pageUrl: args.pageUrl,
    distributionUrl: args.distributionUrl,
    name: args.datasetName,
    description: args.datasetDescription,
    snapshot,
    publisher: args.publisher,
  });

  return {
    snapshot,
    generatedLocal,
    topGuests,
    topWorks,
    distributionBars,
    monthlyBars,
    jsonLd,
  };
}

/**
 * Formate `generatedAt` (ISO UTC) en chaîne lisible FR, locale fixée côté
 * build pour éviter la dérive runtime Intl (M26-20).
 */
function formatGeneratedAt(generatedAt: string, locale = 'fr-FR'): string {
  try {
    const d = new Date(generatedAt);
    if (Number.isNaN(d.getTime())) return generatedAt;
    return new Intl.DateTimeFormat(locale, {
      day: '2-digit',
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(d);
  } catch {
    return generatedAt;
  }
}
