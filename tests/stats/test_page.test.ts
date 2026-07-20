/**
 * Tests pour `src/lib/stats/page.ts` (JSON-LD Dataset).
 */
import { describe, expect, it } from 'vitest';
import { loadStatsForPage, statsDatasetSchema } from '../../src/lib/stats/page';
import { STATS_SCHEMA_VERSION } from '../../src/lib/stats/types';

const snapshot = {
  schemaVersion: STATS_SCHEMA_VERSION,
  generatedAt: '2026-06-12T07:45:00Z',
  global: {
    podcastsCount: 2,
    episodesCount: 104,
    recommendationsCount: 2866,
    uniqueWorksCount: 2651,
    uniqueGuestsCount: 224,
  },
  monthlyEpisodes: [
    { month: '2024-01', count: 4 },
    { month: '2026-05', count: 3 },
  ],
};

describe('statsDatasetSchema', () => {
  it('produit un Dataset schema.org valide', () => {
    const ds = statsDatasetSchema({
      pageUrl: 'https://example.fr/stats',
      name: 'Statistiques publiques',
      description: 'Compteurs Reco.',
      snapshot,
    });
    expect(ds['@context']).toBe('https://schema.org');
    expect(ds['@type']).toBe('Dataset');
    expect(ds.dateModified).toBe('2026-06-12T07:45:00Z');
    expect(ds.url).toBe('https://example.fr/stats');
    expect(Array.isArray(ds.variableMeasured)).toBe(true);
  });

  it('omet la distribution si pas fournie', () => {
    const ds = statsDatasetSchema({
      pageUrl: 'https://x.fr/stats',
      name: 'n',
      description: 'd',
      snapshot,
    });
    expect(ds.distribution).toBeUndefined();
  });

  it('inclut une DataDownload si distributionUrl est fourni (M26-17)', () => {
    const ds = statsDatasetSchema({
      pageUrl: 'https://x.fr/stats',
      distributionUrl: 'https://x.fr/stats.json',
      name: 'n',
      description: 'd',
      snapshot,
    });
    const dist = ds.distribution as Array<Record<string, unknown>>;
    expect(dist).toHaveLength(1);
    expect(dist[0].contentUrl).toBe('https://x.fr/stats.json');
    expect(dist[0].encodingFormat).toBe('application/json');
  });

  it('expose keywords + license + publisher (M26-16/M26-18)', () => {
    const ds = statsDatasetSchema({
      pageUrl: 'https://x.fr/stats',
      name: 'n',
      description: 'd',
      snapshot,
      publisher: { name: 'Mon Kit', url: 'https://x.fr' },
    });
    expect(Array.isArray(ds.keywords)).toBe(true);
    expect((ds.keywords as string[]).length).toBeGreaterThan(0);
    expect(ds.license).toMatch(/MIT/i);
    const publisher = ds.publisher as Record<string, unknown>;
    expect(publisher.name).toBe('Mon Kit');
    expect(publisher.url).toBe('https://x.fr');
    expect(ds.creator).toEqual(publisher);
  });

  it('utilise un publisher par défaut "Reco" si non fourni', () => {
    const ds = statsDatasetSchema({
      pageUrl: 'https://x.fr/stats',
      name: 'n',
      description: 'd',
      snapshot,
    });
    expect((ds.publisher as { name: string }).name).toBe('Reco');
  });

  it("expose temporalCoverage depuis monthlyEpisodes (M26-16)", () => {
    const ds = statsDatasetSchema({
      pageUrl: 'https://x.fr/stats',
      name: 'n',
      description: 'd',
      snapshot,
    });
    expect(ds.temporalCoverage).toBe('2024-01/2026-05');
  });

  it('omet temporalCoverage si aucun mois fourni', () => {
    const ds = statsDatasetSchema({
      pageUrl: 'https://x.fr/stats',
      name: 'n',
      description: 'd',
      snapshot: { generatedAt: snapshot.generatedAt, global: snapshot.global },
    });
    expect(ds.temporalCoverage).toBeUndefined();
  });

  it('expose variableMeasured pour chaque clé de global (F-M-13)', () => {
    const ds = statsDatasetSchema({
      pageUrl: 'https://x.fr/stats',
      name: 'n',
      description: 'd',
      snapshot,
    });
    const vars = ds.variableMeasured as Array<{ name: string; value: number }>;
    const names = vars.map((v) => v.name);
    expect(names).toEqual([
      'podcastsCount',
      'episodesCount',
      'recommendationsCount',
      'uniqueWorksCount',
      'uniqueGuestsCount',
    ]);
    expect(vars[0].value).toBe(2);
  });

  it('accepte une licence custom (fork)', () => {
    const ds = statsDatasetSchema({
      pageUrl: 'https://x.fr/stats',
      name: 'n',
      description: 'd',
      snapshot,
      license: 'https://creativecommons.org/licenses/by/4.0/',
    });
    expect(ds.license).toContain('creativecommons');
  });
});

// --- F-H-6 — loadStatsForPage ----------------------------------------------

describe('loadStatsForPage (F-H-6)', () => {
  const collections = {
    sources: [{ id: 'ubm', hosts: ['Kyan'] }],
    episodes: [
      { sourceId: 'ubm', date: new Date('2026-05-01T00:00:00Z') },
      { sourceId: 'ubm', date: new Date('2026-06-01T00:00:00Z') },
    ],
    mentions: [
      { itemId: 'parasite', recommendedBy: 'Alice', status: 'validated' as const, sourceRef: { sourceId: 'ubm' } },
      { itemId: 'parasite', recommendedBy: 'Bob', status: 'validated' as const, sourceRef: { sourceId: 'ubm' } },
    ],
    items: [
      { id: 'parasite', title: 'Parasite', types: ['film'] as const },
    ],
  };

  it('compute snapshot via buildStatsSnapshot et dérive les view models', () => {
    const r = loadStatsForPage({
      collections,
      pageUrl: 'https://reco.example/stats',
      datasetName: 'Stats',
      datasetDescription: 'desc',
    });
    expect(r.snapshot.global.podcastsCount).toBe(1);
    expect(r.snapshot.global.recommendationsCount).toBe(2);
    expect(r.topGuests.map((g) => g.label)).toEqual(['Alice', 'Bob']);
    expect(r.topWorks[0]).toEqual({ label: 'Parasite', count: 2, sub: 'film' });
    expect(r.distributionBars).toEqual([{ label: 'film', value: 1 }]);
    expect(r.monthlyBars).toEqual([
      { label: '2026-05', value: 1 },
      { label: '2026-06', value: 1 },
    ]);
    expect((r.jsonLd as Record<string, unknown>)['@type']).toBe('Dataset');
  });

  it('respecte le sidecar si fourni — pas de recompute', () => {
    const sidecar = {
      schemaVersion: STATS_SCHEMA_VERSION as 1,
      generatedAt: '2026-06-12T08:00:00Z',
      global: {
        podcastsCount: 42,
        episodesCount: 0,
        recommendationsCount: 0,
        uniqueWorksCount: 0,
        uniqueGuestsCount: 0,
      },
      perSource: {},
      topGuests: [],
      topWorks: [],
      typeDistribution: {},
      monthlyEpisodes: [],
    };
    const r = loadStatsForPage({
      sidecar,
      collections,
      pageUrl: 'https://x.fr/stats',
      datasetName: 'Stats',
      datasetDescription: 'desc',
    });
    expect(r.snapshot.global.podcastsCount).toBe(42); // sidecar, pas recompute
  });

  it('filtre par sourceId quand fourni', () => {
    const r = loadStatsForPage({
      sourceId: 'ubm',
      collections: {
        ...collections,
        sources: [
          { id: 'ubm', hosts: ['Kyan'] },
          { id: 'autre', hosts: [] },
        ],
      },
      pageUrl: 'https://x.fr/ubm/stats',
      datasetName: 'Stats',
      datasetDescription: 'desc',
    });
    expect(Object.keys(r.snapshot.perSource)).toEqual(['ubm']);
  });

  it('formate generatedLocal en FR par défaut (locale fixée)', () => {
    const sidecar = {
      schemaVersion: STATS_SCHEMA_VERSION as 1,
      generatedAt: '2026-06-12T08:00:00Z',
      global: {
        podcastsCount: 0, episodesCount: 0, recommendationsCount: 0,
        uniqueWorksCount: 0, uniqueGuestsCount: 0,
      },
      perSource: {},
      topGuests: [],
      topWorks: [],
      typeDistribution: {},
      monthlyEpisodes: [],
    };
    const r = loadStatsForPage({
      sidecar,
      collections,
      pageUrl: 'https://x.fr/stats',
      datasetName: 'Stats',
      datasetDescription: 'desc',
    });
    // Pas d'assertion sur le texte exact (l'ICU peut varier), juste qu'il
    // n'a pas renvoyé la string ISO brute.
    expect(r.generatedLocal).not.toBe('2026-06-12T08:00:00Z');
    expect(r.generatedLocal).toMatch(/2026/);
  });

  it('fallback sur la string ISO si generatedAt est invalide', () => {
    const sidecar = {
      schemaVersion: STATS_SCHEMA_VERSION as 1,
      generatedAt: '2026-06-12T08:00:00Z',
      global: {
        podcastsCount: 0, episodesCount: 0, recommendationsCount: 0,
        uniqueWorksCount: 0, uniqueGuestsCount: 0,
      },
      perSource: {},
      topGuests: [],
      topWorks: [],
      typeDistribution: {},
      monthlyEpisodes: [],
    };
    // Cast pour forcer une string non parseable :
    const broken = { ...sidecar, generatedAt: 'pas-iso' };
    const r = loadStatsForPage({
      sidecar: broken as typeof sidecar,
      collections,
      pageUrl: 'https://x.fr/stats',
      datasetName: 'Stats',
      datasetDescription: 'desc',
    });
    expect(r.generatedLocal).toBe('pas-iso');
  });

  it('respecte topListLimit', () => {
    const r = loadStatsForPage({
      collections,
      pageUrl: 'https://x.fr/stats',
      datasetName: 'Stats',
      datasetDescription: 'desc',
      topListLimit: 1,
    });
    expect(r.topGuests).toHaveLength(1);
  });
});
