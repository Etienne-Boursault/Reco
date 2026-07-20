/**
 * Tests pour `src/lib/stats/aggregator.ts`.
 */
import { describe, expect, it } from 'vitest';
import {
  buildStatsSnapshot,
  computeGlobalCounts,
  computeMonthlyEpisodes,
  computePerSource,
  computeTopGuests,
  computeTopWorks,
  computeTypeDistribution,
  publicMentions,
  MONTH_MIN_YEAR,
  MONTH_MAX_YEAR,
  MONTHLY_WINDOW_MAX,
} from '../../src/lib/stats/aggregator';
import { STATS_SCHEMA_VERSION } from '../../src/lib/stats/types';

const sources = [
  { id: 'ubm', hosts: ['Kyan'] },
  { id: 'autre', hosts: [] },
];

const episodes = [
  { sourceId: 'ubm', date: new Date('2024-01-15') },
  { sourceId: 'ubm', date: new Date('2024-01-25') },
  { sourceId: 'ubm', date: new Date('2024-02-10') },
  { sourceId: 'autre', date: new Date('2024-02-20') },
  { sourceId: 'ubm', date: null }, // ignoré pour monthly
];

const items = [
  { id: 'parasite', title: 'Parasite', types: ['film'] as const },
  { id: 'dune', title: 'Dune', types: ['film', 'livre'] as const },
  { id: 'sapiens', title: 'Sapiens', types: ['livre'] as const },
  { id: 'orphan', title: 'Orphan', types: ['film'] as const }, // pas de mention
];

const mentions = [
  { itemId: 'parasite', recommendedBy: 'Alice', status: 'validated' as const, sourceRef: { sourceId: 'ubm' } },
  { itemId: 'parasite', recommendedBy: 'Bob', status: 'validated' as const, sourceRef: { sourceId: 'ubm' } },
  { itemId: 'parasite', recommendedBy: 'Alice', status: 'discarded' as const, sourceRef: { sourceId: 'ubm' } }, // exclu
  { itemId: 'dune', recommendedBy: 'Alice', status: 'validated' as const, sourceRef: { sourceId: 'ubm' } },
  { itemId: 'sapiens', recommendedBy: 'Kyan', status: 'validated' as const, sourceRef: { sourceId: 'ubm' } }, // host exclu de guests
  { itemId: 'sapiens', recommendedBy: 'Bob', status: 'validated' as const, sourceRef: { sourceId: 'autre' } },
  { itemId: 'sapiens', recommendedBy: null, status: 'validated' as const, sourceRef: { sourceId: 'autre' } },
];

describe('publicMentions', () => {
  it('exclut les discarded', () => {
    expect(publicMentions(mentions)).toHaveLength(6);
  });
});

describe('computeGlobalCounts', () => {
  it('calcule les compteurs globaux corrects', () => {
    const g = computeGlobalCounts({ sources, episodes, mentions, items });
    expect(g.podcastsCount).toBe(2);
    expect(g.episodesCount).toBe(5);
    expect(g.recommendationsCount).toBe(6);
    // parasite, dune, sapiens — orphan exclu (pas de mention)
    expect(g.uniqueWorksCount).toBe(3);
    // Alice, Bob — Kyan est host (exclu) ; null ignoré
    expect(g.uniqueGuestsCount).toBe(2);
  });

  it('renvoie tous les compteurs à 0 sur entrée vide', () => {
    const g = computeGlobalCounts({ sources: [], episodes: [], mentions: [], items: [] });
    expect(g).toEqual({
      podcastsCount: 0,
      episodesCount: 0,
      recommendationsCount: 0,
      uniqueWorksCount: 0,
      uniqueGuestsCount: 0,
    });
  });
});

describe('computeTopGuests', () => {
  it('trie par count DESC puis nom ASC (locale FR)', () => {
    const top = computeTopGuests(mentions, sources, 10);
    // Alice = 2 (parasite + dune), Bob = 2 (parasite + sapiens)
    // (Kyan exclu — host). Égalité → tri alpha → Alice avant Bob.
    expect(top[0].name).toBe('Alice');
    expect(top[0].count).toBe(2);
    expect(top[0].slug).toBe('alice');
    expect(top[1].name).toBe('Bob');
    expect(top[1].count).toBe(2);
  });

  it('respecte la limite', () => {
    expect(computeTopGuests(mentions, sources, 1)).toHaveLength(1);
  });

  it('exclut les mentions discarded', () => {
    const top = computeTopGuests(mentions, sources, 10);
    const alice = top.find((g) => g.name === 'Alice');
    // 1 discarded + 2 validated → count = 2
    expect(alice?.count).toBe(2);
  });
});

describe('computeTopWorks', () => {
  it('trie par mentions DESC puis titre ASC', () => {
    const top = computeTopWorks(items, mentions, 10);
    // sapiens = 3 (Kyan host inclus dans le count œuvre, null inclus, Bob)
    // parasite = 2 (Alice + Bob, Alice discarded exclu)
    // dune = 1
    expect(top[0].id).toBe('sapiens');
    expect(top[0].mentionsCount).toBe(3);
    expect(top[0].type).toBe('livre');
    expect(top[1].id).toBe('parasite');
    expect(top[1].mentionsCount).toBe(2);
    expect(top[2].id).toBe('dune');
  });

  it('ignore les mentions orphelines (item inconnu)', () => {
    const m = [...mentions, { itemId: 'ghost', sourceRef: { sourceId: 'ubm' } }];
    const top = computeTopWorks(items, m, 10);
    expect(top.map((t) => t.id)).not.toContain('ghost');
  });
});

describe('computeTypeDistribution', () => {
  it('compte une œuvre par type principal', () => {
    const d = computeTypeDistribution(items, mentions);
    // parasite=film, dune=film (types[0]), sapiens=livre → film:2, livre:1
    expect(d).toEqual({ film: 2, livre: 1 });
  });

  it('retourne {} si rien à compter', () => {
    expect(computeTypeDistribution([], [])).toEqual({});
  });
});

describe('computeMonthlyEpisodes', () => {
  it('agrège par mois et trie ASC', () => {
    const buckets = computeMonthlyEpisodes(episodes);
    expect(buckets).toEqual([
      { month: '2024-01', count: 2 },
      { month: '2024-02', count: 2 },
    ]);
  });

  it('accepte ISO string et Date, ignore les dates absentes', () => {
    const buckets = computeMonthlyEpisodes([
      { sourceId: 'x', date: '2026-03-01T00:00:00Z' },
      { sourceId: 'x', date: undefined },
      { sourceId: 'x', date: 'pas une date' },
    ]);
    expect(buckets).toEqual([{ month: '2026-03', count: 1 }]);
  });
});

describe('computePerSource', () => {
  it('produit un compteur global par source', () => {
    const ps = computePerSource({ sources, episodes, mentions, items });
    expect(ps.ubm.episodesCount).toBe(4);
    expect(ps.ubm.recommendationsCount).toBe(4); // parasite x2 + dune + sapiens
    expect(ps.autre.episodesCount).toBe(1);
    expect(ps.autre.recommendationsCount).toBe(2);
  });
});

describe('buildStatsSnapshot', () => {
  it('produit un snapshot complet et déterministe', () => {
    const snap = buildStatsSnapshot({
      sources,
      episodes,
      mentions,
      items,
      options: { generatedAt: '2026-06-12T00:00:00Z' },
    });
    expect(snap.schemaVersion).toBe(STATS_SCHEMA_VERSION);
    expect(snap.generatedAt).toBe('2026-06-12T00:00:00Z');
    expect(snap.global.podcastsCount).toBe(2);
    expect(snap.topGuests.length).toBeGreaterThan(0);
    expect(snap.monthlyEpisodes.length).toBeGreaterThan(0);
  });

  it('filtre par source quand sourceId est fourni', () => {
    const snap = buildStatsSnapshot({
      sources,
      episodes,
      mentions,
      items,
      options: { sourceId: 'ubm', generatedAt: 'now' },
    });
    expect(snap.global.podcastsCount).toBe(1);
    expect(snap.global.episodesCount).toBe(4);
    expect(Object.keys(snap.perSource)).toEqual(['ubm']);
  });

  it('utilise une valeur par défaut pour generatedAt si non fournie', () => {
    const snap = buildStatsSnapshot({ sources: [], episodes: [], mentions: [], items: [] });
    expect(snap.generatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });
});

// --- F-CRIT-9 — cap fenêtre monthly ------------------------------------------

describe('computeMonthlyEpisodes — F-CRIT-9 cap fenêtre', () => {
  it('expose la constante MONTHLY_WINDOW_MAX = 60', () => {
    expect(MONTHLY_WINDOW_MAX).toBe(60);
  });

  it('cap la fenêtre à 60 mois quand la plage min↔max est trop large', () => {
    // 2 épisodes : un en 1995, un en 2026 → sans cap ~370 buckets.
    const buckets = computeMonthlyEpisodes([
      { sourceId: 'x', date: new Date('1995-03-15T00:00:00Z') },
      { sourceId: 'x', date: new Date('2026-06-10T00:00:00Z') },
    ]);
    // Cappé à 60 mois → premier bucket = 2021-07.
    expect(buckets).toHaveLength(60);
    expect(buckets[0]).toEqual({ month: '2021-07', count: 0 });
    expect(buckets[buckets.length - 1]).toEqual({ month: '2026-06', count: 1 });
  });

  it("conserve l'intervalle complet quand il est dans la fenêtre", () => {
    const buckets = computeMonthlyEpisodes([
      { sourceId: 'x', date: new Date('2026-01-15T00:00:00Z') },
      { sourceId: 'x', date: new Date('2026-03-20T00:00:00Z') },
    ]);
    expect(buckets).toEqual([
      { month: '2026-01', count: 1 },
      { month: '2026-02', count: 0 },
      { month: '2026-03', count: 1 },
    ]);
  });

  it('exclut les épisodes hors bornes MIN/MAX year', () => {
    expect(MONTH_MIN_YEAR).toBe(1900);
    expect(MONTH_MAX_YEAR).toBe(2100);
    const buckets = computeMonthlyEpisodes([
      { sourceId: 'x', date: '0001-01-01T00:00:00Z' },
      { sourceId: 'x', date: '9999-01-01T00:00:00Z' },
    ]);
    expect(buckets).toEqual([]);
  });
});

// --- F-CRIT-4 — generatedAt déterministe via env vars ------------------------

describe('buildStatsSnapshot — F-CRIT-4 generatedAt depuis env', () => {
  it('utilise SOURCE_DATE_EPOCH si présent (priorité 1)', () => {
    const prev = {
      epoch: process.env.SOURCE_DATE_EPOCH,
      ts: process.env.RECO_BUILD_TIMESTAMP,
    };
    process.env.SOURCE_DATE_EPOCH = '1717200000'; // 2024-06-01T00:00:00Z
    process.env.RECO_BUILD_TIMESTAMP = '2099-01-01T00:00:00Z';
    try {
      const snap = buildStatsSnapshot({
        sources: [], episodes: [], mentions: [], items: [],
      });
      expect(snap.generatedAt).toBe(new Date(1717200000 * 1000).toISOString());
    } finally {
      if (prev.epoch === undefined) delete process.env.SOURCE_DATE_EPOCH;
      else process.env.SOURCE_DATE_EPOCH = prev.epoch;
      if (prev.ts === undefined) delete process.env.RECO_BUILD_TIMESTAMP;
      else process.env.RECO_BUILD_TIMESTAMP = prev.ts;
    }
  });

  it('utilise RECO_BUILD_TIMESTAMP si SOURCE_DATE_EPOCH absent (priorité 2)', () => {
    const prev = {
      epoch: process.env.SOURCE_DATE_EPOCH,
      ts: process.env.RECO_BUILD_TIMESTAMP,
    };
    delete process.env.SOURCE_DATE_EPOCH;
    process.env.RECO_BUILD_TIMESTAMP = '2026-06-12T07:00:00Z';
    try {
      const snap = buildStatsSnapshot({
        sources: [], episodes: [], mentions: [], items: [],
      });
      expect(snap.generatedAt).toBe('2026-06-12T07:00:00Z');
    } finally {
      if (prev.epoch !== undefined) process.env.SOURCE_DATE_EPOCH = prev.epoch;
      if (prev.ts === undefined) delete process.env.RECO_BUILD_TIMESTAMP;
      else process.env.RECO_BUILD_TIMESTAMP = prev.ts;
    }
  });

  it('options.generatedAt > env > new Date()', () => {
    const prev = process.env.SOURCE_DATE_EPOCH;
    process.env.SOURCE_DATE_EPOCH = '1717200000';
    try {
      const snap = buildStatsSnapshot({
        sources: [], episodes: [], mentions: [], items: [],
        options: { generatedAt: '2030-01-01T00:00:00Z' },
      });
      expect(snap.generatedAt).toBe('2030-01-01T00:00:00Z');
    } finally {
      if (prev === undefined) delete process.env.SOURCE_DATE_EPOCH;
      else process.env.SOURCE_DATE_EPOCH = prev;
    }
  });

  it('ignore SOURCE_DATE_EPOCH non-numérique', () => {
    const prev = {
      epoch: process.env.SOURCE_DATE_EPOCH,
      ts: process.env.RECO_BUILD_TIMESTAMP,
    };
    process.env.SOURCE_DATE_EPOCH = 'pas-un-nombre';
    delete process.env.RECO_BUILD_TIMESTAMP;
    try {
      const snap = buildStatsSnapshot({
        sources: [], episodes: [], mentions: [], items: [],
      });
      expect(snap.generatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    } finally {
      if (prev.epoch === undefined) delete process.env.SOURCE_DATE_EPOCH;
      else process.env.SOURCE_DATE_EPOCH = prev.epoch;
      if (prev.ts !== undefined) process.env.RECO_BUILD_TIMESTAMP = prev.ts;
    }
  });
});

// --- F-H-14 — top guests : forme la plus fréquente ---------------------------

describe('computeTopGuests — F-H-14 dédup nom', () => {
  it('conserve la forme la plus fréquente du name', () => {
    const m = [
      { itemId: 'a', recommendedBy: 'Alice', status: 'validated' as const, sourceRef: { sourceId: 'x' } },
      { itemId: 'a', recommendedBy: 'Alice', status: 'validated' as const, sourceRef: { sourceId: 'x' } },
      { itemId: 'a', recommendedBy: 'alice', status: 'validated' as const, sourceRef: { sourceId: 'x' } },
    ];
    const top = computeTopGuests(m, [], 5);
    expect(top[0].name).toBe('Alice'); // 2 occurrences vs 1
    expect(top[0].count).toBe(3);
  });

  it('en cas de tie, préfère la version capitalisée', () => {
    const m = [
      { itemId: 'a', recommendedBy: 'alice', status: 'validated' as const, sourceRef: { sourceId: 'x' } },
      { itemId: 'a', recommendedBy: 'Alice', status: 'validated' as const, sourceRef: { sourceId: 'x' } },
    ];
    const top = computeTopGuests(m, [], 5);
    expect(top[0].name).toBe('Alice');
  });
});
