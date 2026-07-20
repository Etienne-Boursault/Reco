/**
 * Tests du schema Zod `RegistryDocument` (`src/lib/registry/types.ts`).
 */
import { describe, it, expect } from 'vitest';
import {
  REGISTRY_SCHEMA_VERSION,
  parseRegistry,
  tryParseRegistry,
} from '../../src/lib/registry/types.js';

const validDoc = {
  schemaVersion: 1,
  siteUrl: 'https://un-bon-moment.example.com',
  podcast: {
    title: 'Un Bon Moment',
    tagline: 'Les recos de Kyan & Navo',
    rssUrl: 'https://feeds.acast.com/public/shows/xyz',
    hosts: ['Kyan Khojandi', 'Navo'],
    since: '2018-09-01',
    language: 'fr',
  },
  stats: {
    itemsCount: 2651,
    mentionsCount: 2866,
    episodesCount: 104,
    guestsCount: 224,
    lastUpdatedAt: '2026-06-12T00:00:00Z',
  },
  meta: {
    generator: 'Reco/0.3.0',
    generatedAt: '2026-06-12T07:45:00Z',
    manifesto: 'https://un-bon-moment.example.com/manifeste',
  },
  endpoints: {
    ogImage: '/og/default.png',
    sitemap: '/sitemap-index.xml',
    search: '/search.json',
  },
};

describe('REGISTRY_SCHEMA_VERSION', () => {
  it('est figé à 1 (bump = ADR)', () => {
    expect(REGISTRY_SCHEMA_VERSION).toBe(1);
  });
});

describe('parseRegistry — happy paths', () => {
  it('accepte un document complet', () => {
    const out = parseRegistry(validDoc);
    expect(out.podcast.title).toBe('Un Bon Moment');
    expect(out.stats.mentionsCount).toBe(2866);
  });

  it('applique le default `endpoints: {}` si omis', () => {
    const { endpoints: _omit, ...withoutEndpoints } = validDoc;
    const out = parseRegistry(withoutEndpoints);
    expect(out.endpoints).toEqual({});
  });

  it('applique le default `hosts: []` si omis', () => {
    const out = parseRegistry({
      ...validDoc,
      podcast: { title: 'X', language: 'fr' },
    });
    expect(out.podcast.hosts).toEqual([]);
  });
});

describe('parseRegistry — validation', () => {
  it('rejette schemaVersion ≠ 1', () => {
    expect(() => parseRegistry({ ...validDoc, schemaVersion: 2 })).toThrow();
  });

  it('rejette une siteUrl HTTP en production (F-H-8)', () => {
    const prev = process.env.NODE_ENV;
    process.env.NODE_ENV = 'production';
    try {
      expect(() =>
        parseRegistry({ ...validDoc, siteUrl: 'http://insecure.example' }),
      ).toThrow();
    } finally {
      process.env.NODE_ENV = prev;
    }
  });

  it('tolère une siteUrl HTTP hors production (F-H-8)', () => {
    const prev = process.env.NODE_ENV;
    process.env.NODE_ENV = 'development';
    try {
      expect(() =>
        parseRegistry({ ...validDoc, siteUrl: 'http://localhost:4321' }),
      ).not.toThrow();
    } finally {
      process.env.NODE_ENV = prev;
    }
  });

  it('rejette une langue non ISO 639-1', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        podcast: { ...validDoc.podcast, language: 'fra' },
      }),
    ).toThrow();
  });

  it('rejette des compteurs négatifs', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        stats: { ...validDoc.stats, itemsCount: -1 },
      }),
    ).toThrow();
  });

  it('rejette un generatedAt non-ISO', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        meta: { ...validDoc.meta, generatedAt: 'hier matin' },
      }),
    ).toThrow();
  });

  it('rejette une `since` mal formée', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        podcast: { ...validDoc.podcast, since: '2018' },
      }),
    ).toThrow();
  });
});

describe('parseRegistry — strict mode + bornes (H24-2 / M24-5..7)', () => {
  it('rejette un champ inconnu à la racine (.strict)', () => {
    expect(() => parseRegistry({ ...validDoc, extra: 1 })).toThrow();
  });

  it('rejette un champ inconnu dans podcast', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        podcast: { ...validDoc.podcast, secretField: 'x' },
      }),
    ).toThrow();
  });

  it('rejette un champ inconnu dans stats', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        stats: { ...validDoc.stats, extra: 1 },
      }),
    ).toThrow();
  });

  it('rejette title trop long (M24-6)', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        podcast: { ...validDoc.podcast, title: 'a'.repeat(201) },
      }),
    ).toThrow();
  });

  it('rejette > 64 hosts (M24-5)', () => {
    const hosts = Array.from({ length: 65 }, (_, i) => `Host ${i}`);
    expect(() =>
      parseRegistry({ ...validDoc, podcast: { ...validDoc.podcast, hosts } }),
    ).toThrow();
  });

  it('rejette un host > 200 chars (M24-5)', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        podcast: { ...validDoc.podcast, hosts: ['x'.repeat(201)] },
      }),
    ).toThrow();
  });

  it('accepte un endpoint chemin absolu', () => {
    const doc = parseRegistry({
      ...validDoc,
      endpoints: { ogImage: '/og/custom.png' },
    });
    expect(doc.endpoints.ogImage).toBe('/og/custom.png');
  });

  it('accepte un endpoint URL HTTPS', () => {
    const doc = parseRegistry({
      ...validDoc,
      endpoints: { ogImage: 'https://cdn.example/x.png' },
    });
    expect(doc.endpoints.ogImage).toBe('https://cdn.example/x.png');
  });

  it('rejette un endpoint http (M24-7)', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        endpoints: { ogImage: 'http://insecure/x' },
      }),
    ).toThrow();
  });

  it('rejette une seconde 60 dans generatedAt (L24-21)', () => {
    expect(() =>
      parseRegistry({
        ...validDoc,
        meta: { ...validDoc.meta, generatedAt: '2026-06-12T07:45:60Z' },
      }),
    ).toThrow();
  });

  it('accepte le champ optionnel podcasts (R-P1-05)', () => {
    const doc = parseRegistry({
      ...validDoc,
      podcasts: [{ title: 'B', hosts: [], language: 'fr' }],
    });
    expect(doc.podcasts?.[0].title).toBe('B');
  });
});

describe('tryParseRegistry', () => {
  it('renvoie ok=true sur document valide', () => {
    const r = tryParseRegistry(validDoc);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.siteUrl).toBe(validDoc.siteUrl);
  });

  it('renvoie ok=false avec un message en cas d’échec', () => {
    const r = tryParseRegistry({ ...validDoc, siteUrl: 'not-a-url' });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.length).toBeGreaterThan(0);
  });
});
