/**
 * Tests des schémas Zod pour `stats.json` (frontière de la persistance).
 */
import { describe, expect, it } from 'vitest';
import {
  STATS_SCHEMA_VERSION,
  statsSnapshotSchema,
  topGuestSchema,
  monthlyBucketSchema,
} from '../../src/lib/stats/types';

const valid = {
  schemaVersion: STATS_SCHEMA_VERSION,
  generatedAt: '2026-06-12T07:45:00Z',
  global: {
    podcastsCount: 1,
    episodesCount: 10,
    recommendationsCount: 100,
    uniqueWorksCount: 80,
    uniqueGuestsCount: 12,
  },
  perSource: {
    'un-bon-moment': {
      podcastsCount: 1,
      episodesCount: 10,
      recommendationsCount: 100,
      uniqueWorksCount: 80,
      uniqueGuestsCount: 12,
    },
  },
  topGuests: [{ name: 'Alice', slug: 'alice', count: 3 }],
  topWorks: [{ id: 'parasite', title: 'Parasite', type: 'film', mentionsCount: 3 }],
  typeDistribution: { film: 5, livre: 3 },
  monthlyEpisodes: [{ month: '2024-01', count: 4 }],
};

describe('statsSnapshotSchema', () => {
  it('valide un snapshot conforme', () => {
    expect(() => statsSnapshotSchema.parse(valid)).not.toThrow();
  });

  it('rejette un schemaVersion incorrect', () => {
    expect(() => statsSnapshotSchema.parse({ ...valid, schemaVersion: 99 })).toThrow();
  });

  it('rejette les counts négatifs', () => {
    const bad = { ...valid, global: { ...valid.global, podcastsCount: -1 } };
    expect(() => statsSnapshotSchema.parse(bad)).toThrow();
  });

  it('rejette les clés inconnues (.strict() — H26-1)', () => {
    expect(() => statsSnapshotSchema.parse({ ...valid, foo: 'bar' })).toThrow();
    const bad = { ...valid, global: { ...valid.global, extra: 1 } };
    expect(() => statsSnapshotSchema.parse(bad)).toThrow();
  });

  it('rejette un generatedAt non-ISO 8601 UTC (M26-5)', () => {
    const bad = { ...valid, generatedAt: '2026-06-12 07:45' };
    expect(() => statsSnapshotSchema.parse(bad)).toThrow();
    const bad2 = { ...valid, generatedAt: '2026-06-12T07:45:00+02:00' };
    expect(() => statsSnapshotSchema.parse(bad2)).toThrow();
  });

  it('accepte fractions de seconde dans generatedAt', () => {
    const ok = { ...valid, generatedAt: '2026-06-12T07:45:00.123Z' };
    expect(() => statsSnapshotSchema.parse(ok)).not.toThrow();
  });
});

describe('monthlyBucketSchema', () => {
  it('valide le format YYYY-MM', () => {
    expect(() => monthlyBucketSchema.parse({ month: '2026-01', count: 1 })).not.toThrow();
  });

  it('rejette un mois mal formé', () => {
    expect(() => monthlyBucketSchema.parse({ month: '2026/01', count: 1 })).toThrow();
    expect(() => monthlyBucketSchema.parse({ month: '2026-1', count: 1 })).toThrow();
  });
});

describe('topGuestSchema', () => {
  it('exige name + slug non vides', () => {
    expect(() => topGuestSchema.parse({ name: '', slug: 'x', count: 0 })).toThrow();
    expect(() => topGuestSchema.parse({ name: 'A', slug: '', count: 0 })).toThrow();
  });
});
