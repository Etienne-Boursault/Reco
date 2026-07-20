/**
 * Tests du consumer (méta-site).
 */
import { describe, it, expect, vi } from 'vitest';
import {
  buildEntries,
  slugFromSiteUrl,
  sortEntries,
  findEntry,
  aggregateTotals,
  dedupeBySlug,
} from '../../src/lib/registry/consumer.js';

const validRegistry = (overrides: Record<string, unknown> = {}) => ({
  schemaVersion: 1,
  siteUrl: 'https://un-bon-moment.example.com',
  podcast: { title: 'Un Bon Moment', hosts: [], language: 'fr' },
  stats: {
    itemsCount: 10,
    mentionsCount: 12,
    episodesCount: 5,
    guestsCount: 4,
    lastUpdatedAt: '2026-06-12T00:00:00Z',
  },
  meta: { generator: 'Reco/0.3.0', generatedAt: '2026-06-12T07:45:00Z' },
  endpoints: {},
  ...overrides,
});

describe('slugFromSiteUrl', () => {
  it('extrait le host (lowercase, sans www)', () => {
    expect(slugFromSiteUrl('https://www.Un-Bon-Moment.example.com/')).toBe(
      'un-bon-moment.example.com',
    );
  });

  it('ignore le port', () => {
    expect(slugFromSiteUrl('https://host.example:8443/x')).toBe('host.example');
  });

  it('fallback déterministe pour input invalide', () => {
    expect(slugFromSiteUrl('not a url!')).toBe('not-a-url');
  });

  it('retourne "unknown" si rien ne peut être extrait (M24-11)', () => {
    expect(slugFromSiteUrl('!!!')).toBe('unknown');
    expect(slugFromSiteUrl('')).toBe('unknown');
  });

  it('F-L-3 : rejette IPv4 (DNS rebinding / privacy)', () => {
    expect(slugFromSiteUrl('https://192.168.1.10/')).toBe('unknown');
    expect(slugFromSiteUrl('https://10.0.0.1:8080/')).toBe('unknown');
  });

  it('F-L-3 : rejette IPv6 littéral', () => {
    expect(slugFromSiteUrl('https://[::1]/')).toBe('unknown');
  });
});

describe('dedupeBySlug — F-H-13 ordre stable', () => {
  it('le 1er sourceUrl (tri ascendant) gagne en cas de doublon', async () => {
    const { dedupeBySlug } = await import('../../src/lib/registry/consumer.js');
    const e = (sourceUrl: string): unknown => ({
      sourceUrl,
      slug: 'same',
      registry: validRegistry({ siteUrl: 'https://same.example' }),
    });
    // Input ordre arbitraire — la sortie doit toujours présenter
    // le sourceUrl `aaa.example` (premier alpha).
    const out1 = dedupeBySlug([
      e('zzz.example'),
      e('aaa.example'),
      e('mmm.example'),
    ] as never);
    const out2 = dedupeBySlug([
      e('mmm.example'),
      e('zzz.example'),
      e('aaa.example'),
    ] as never);
    expect(out1[0].sourceUrl).toBe('aaa.example');
    expect(out2[0].sourceUrl).toBe('aaa.example');
  });
});

describe('sortEntries — tri NFKD normalisé (L24-23)', () => {
  it('ordonne déterministement même avec accents', () => {
    // Les titres « Étoile » et « Etoile » doivent tomber au même rang
    // d'égalité (équivalence NFKD/casefold).
    const e1 = {
      sourceUrl: 'u1',
      slug: 'a',
      registry: validRegistry({
        siteUrl: 'https://a.example',
        stats: {
          itemsCount: 0,
          mentionsCount: 5,
          episodesCount: 0,
          guestsCount: 0,
          lastUpdatedAt: '2026-06-12T00:00:00Z',
        },
        podcast: { title: 'Étoile', hosts: [], language: 'fr' },
      }),
    } as never;
    const e2 = {
      sourceUrl: 'u2',
      slug: 'b',
      registry: validRegistry({
        siteUrl: 'https://b.example',
        stats: {
          itemsCount: 0,
          mentionsCount: 5,
          episodesCount: 0,
          guestsCount: 0,
          lastUpdatedAt: '2026-06-12T00:00:00Z',
        },
        podcast: { title: 'Apostrophe', hosts: [], language: 'fr' },
      }),
    } as never;
    const sorted = sortEntries([e1, e2]);
    expect(sorted[0].registry.podcast.title).toBe('Apostrophe');
  });
});

describe('buildEntries', () => {
  it('parse + slug les registries valides', () => {
    const entries = buildEntries([
      { sourceUrl: 'https://ubm.example/.well-known/reco-registry.json', registry: validRegistry() },
    ]);
    expect(entries).toHaveLength(1);
    expect(entries[0].slug).toBe('un-bon-moment.example.com');
  });

  it('ignore les registries invalides et reporte', () => {
    const onInvalid = vi.fn();
    const entries = buildEntries(
      [
        { sourceUrl: 'a', registry: { broken: true } },
        { sourceUrl: 'b', registry: validRegistry() },
      ],
      onInvalid,
    );
    expect(entries).toHaveLength(1);
    expect(onInvalid).toHaveBeenCalledTimes(1);
    expect(onInvalid).toHaveBeenCalledWith('a', expect.any(String));
  });

  it('dédoublonne par slug (premier gagne)', () => {
    const a = validRegistry({ siteUrl: 'https://x.example' });
    const b = validRegistry({
      siteUrl: 'https://www.x.example',
      podcast: { title: 'Autre', hosts: [], language: 'fr' },
    });
    const entries = buildEntries([
      { sourceUrl: 'u1', registry: a },
      { sourceUrl: 'u2', registry: b },
    ]);
    expect(entries).toHaveLength(1);
    expect(entries[0].registry.podcast.title).toBe('Un Bon Moment');
  });
});

describe('dedupeBySlug', () => {
  it('n’altère pas un tableau sans doublon', () => {
    const e1 = {
      sourceUrl: 'u',
      slug: 'a',
      registry: validRegistry({ siteUrl: 'https://a.example' }),
    } as never;
    expect(dedupeBySlug([e1])).toHaveLength(1);
  });
});

describe('sortEntries', () => {
  it('trie par mentions desc, tie-break titre asc', () => {
    const e = buildEntries([
      { sourceUrl: 'u1', registry: validRegistry({ siteUrl: 'https://a.example', stats: { itemsCount: 0, mentionsCount: 10, episodesCount: 0, guestsCount: 0, lastUpdatedAt: '2026-06-12T00:00:00Z' }, podcast: { title: 'Beta', hosts: [], language: 'fr' } }) },
      { sourceUrl: 'u2', registry: validRegistry({ siteUrl: 'https://b.example', stats: { itemsCount: 0, mentionsCount: 50, episodesCount: 0, guestsCount: 0, lastUpdatedAt: '2026-06-12T00:00:00Z' }, podcast: { title: 'Charlie', hosts: [], language: 'fr' } }) },
      { sourceUrl: 'u3', registry: validRegistry({ siteUrl: 'https://c.example', stats: { itemsCount: 0, mentionsCount: 50, episodesCount: 0, guestsCount: 0, lastUpdatedAt: '2026-06-12T00:00:00Z' }, podcast: { title: 'Alpha', hosts: [], language: 'fr' } }) },
    ]);
    const sorted = sortEntries(e);
    expect(sorted.map((x) => x.registry.podcast.title)).toEqual(['Alpha', 'Charlie', 'Beta']);
  });
});

describe('findEntry', () => {
  it('retrouve par slug', () => {
    const entries = buildEntries([
      { sourceUrl: 'u', registry: validRegistry({ siteUrl: 'https://podcast.example' }) },
    ]);
    expect(findEntry(entries, 'podcast.example')?.registry.podcast.title).toBe('Un Bon Moment');
    expect(findEntry(entries, 'absent')).toBeUndefined();
  });
});

describe('aggregateTotals', () => {
  it('somme les compteurs', () => {
    const entries = buildEntries([
      { sourceUrl: 'u1', registry: validRegistry({ siteUrl: 'https://a.example' }) },
      { sourceUrl: 'u2', registry: validRegistry({ siteUrl: 'https://b.example' }) },
    ]);
    const totals = aggregateTotals(entries);
    expect(totals).toEqual({ podcasts: 2, items: 20, mentions: 24, episodes: 10, guests: 8 });
  });

  it('zero sur tableau vide', () => {
    expect(aggregateTotals([])).toEqual({
      podcasts: 0, items: 0, mentions: 0, episodes: 0, guests: 0,
    });
  });
});
