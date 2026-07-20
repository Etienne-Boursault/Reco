/**
 * Tests du générateur de registry.
 *
 * Les compteurs viennent de `computeGlobalCounts` (SSOT, X-P0-32) :
 *   - `itemsCount` = uniqueWorks (items mentionnés ∩ catalogue items).
 *   - `mentionsCount` = recommendationsCount (filtre `discarded`).
 *   - `guestsCount` = invités uniques, hors hosts (case-insensitive).
 *   - `episodesCount` = nb d'épisodes injectés.
 */
import { describe, it, expect } from 'vitest';
import { buildRegistry } from '../../src/lib/registry/generator.js';
import { parseRegistry } from '../../src/lib/registry/types.js';

const baseInput = {
  source: {
    id: 'un-bon-moment',
    title: 'Un Bon Moment',
    tagline: 'Les recos de Kyan & Navo',
    hosts: ['Kyan Khojandi', 'Navo'],
    rssUrl: 'https://feeds.acast.com/public/shows/abc',
    language: 'fr',
    since: '2018-09-01',
  },
  episodes: [
    { sourceId: 'un-bon-moment', date: '2024-01-01' },
    { sourceId: 'un-bon-moment', date: '2024-02-01' },
    { sourceId: 'un-bon-moment', date: '2024-03-15' },
  ],
  items: [
    { id: 'item-a', title: 'Œuvre A', types: ['film'] },
    { id: 'item-b', title: 'Œuvre B', types: ['livre'] },
    { id: 'item-c', title: 'Œuvre C', types: ['serie'] },
  ],
  mentions: [
    {
      itemId: 'item-a',
      recommendedBy: 'Alice',
      status: 'validated' as const,
      sourceRef: { sourceId: 'un-bon-moment' },
    },
    {
      itemId: 'item-b',
      recommendedBy: 'Bob',
      status: 'draft' as const,
      sourceRef: { sourceId: 'un-bon-moment' },
    },
    {
      itemId: 'item-c',
      recommendedBy: 'Alice',
      status: 'discarded' as const, // filtré
      sourceRef: { sourceId: 'un-bon-moment' },
    },
    {
      itemId: 'item-a',
      recommendedBy: 'Kyan Khojandi', // host → exclu de guests
      status: 'validated' as const,
      sourceRef: { sourceId: 'un-bon-moment' },
    },
  ],
  siteUrl: 'https://un-bon-moment.example.com',
  generator: 'Reco/0.1.0',
  generatedAt: '2026-06-12T07:45:00Z',
  manifestoUrl: 'https://un-bon-moment.example.com/manifeste',
};

describe('buildRegistry', () => {
  it('produit un document valide (parseRegistry passe)', () => {
    const doc = buildRegistry(baseInput);
    expect(() => parseRegistry(doc)).not.toThrow();
  });

  it('compte les mentions publiques (drop discarded)', () => {
    const doc = buildRegistry(baseInput);
    expect(doc.stats.mentionsCount).toBe(3);
  });

  it('compte les invités hors hosts (X-P0-32)', () => {
    const doc = buildRegistry(baseInput);
    // alice + bob, Kyan Khojandi (host) exclu
    expect(doc.stats.guestsCount).toBe(2);
  });

  it('compte les épisodes via la longueur du tableau', () => {
    const doc = buildRegistry(baseInput);
    expect(doc.stats.episodesCount).toBe(3);
  });

  it('itemsCount = uniqueWorks (R-P1-01)', () => {
    const doc = buildRegistry(baseInput);
    // item-a et item-b mentionnés publics (item-c discarded)
    expect(doc.stats.itemsCount).toBe(2);
  });

  it('utilise generatedAt comme lastUpdatedAt fallback (H24-3)', () => {
    const doc = buildRegistry({ ...baseInput, episodes: [] });
    expect(doc.stats.lastUpdatedAt).toBe(baseInput.generatedAt);
  });

  it('dérive lastUpdatedAt de max(episode.date) (H24-3)', () => {
    const doc = buildRegistry(baseInput);
    expect(doc.stats.lastUpdatedAt.startsWith('2024-03-15')).toBe(true);
  });

  it('respecte lastUpdatedAt explicite', () => {
    const doc = buildRegistry({
      ...baseInput,
      lastUpdatedAt: '2026-06-11T00:00:00Z',
    });
    expect(doc.stats.lastUpdatedAt).toBe('2026-06-11T00:00:00Z');
  });

  it('défaut language=fr si absent', () => {
    const doc = buildRegistry({
      ...baseInput,
      source: { ...baseInput.source, language: undefined },
    });
    expect(doc.podcast.language).toBe('fr');
  });

  it('F-CRIT-8 : normalise language BCP-47 (fr-FR → fr)', () => {
    const doc = buildRegistry({
      ...baseInput,
      source: { ...baseInput.source, language: 'fr-FR' },
    });
    expect(doc.podcast.language).toBe('fr');
  });

  it('F-CRIT-8 : normalise language EN_US → en', () => {
    const doc = buildRegistry({
      ...baseInput,
      source: { ...baseInput.source, language: 'EN_US' },
    });
    expect(doc.podcast.language).toBe('en');
  });

  it('F-CRIT-8 : fallback fr si language vide ou invalide', () => {
    const doc = buildRegistry({
      ...baseInput,
      source: { ...baseInput.source, language: '???' },
    });
    expect(doc.podcast.language).toBe('fr');
  });

  it('propage les endpoints standards', () => {
    const doc = buildRegistry(baseInput);
    expect(doc.endpoints.ogImage).toBe('/og/default.png');
    expect(doc.endpoints.sitemap).toBe('/sitemap-index.xml');
    expect(doc.endpoints.search).toBe('/search.json');
  });

  it('accepte un override partiel des endpoints (R-P1-04)', () => {
    const doc = buildRegistry({
      ...baseInput,
      endpoints: { ogImage: 'https://cdn.example/og.png' },
    });
    expect(doc.endpoints.ogImage).toBe('https://cdn.example/og.png');
    // les autres défauts restent
    expect(doc.endpoints.sitemap).toBe('/sitemap-index.xml');
  });

  it('mentionne le manifeste si fourni', () => {
    const doc = buildRegistry(baseInput);
    expect(doc.meta.manifesto).toBe(baseInput.manifestoUrl);
  });

  it('ignore les épisodes sans date valide pour lastUpdatedAt', () => {
    const doc = buildRegistry({
      ...baseInput,
      episodes: [
        { sourceId: 'un-bon-moment', date: 'pas une date' as unknown as string },
        { sourceId: 'un-bon-moment', date: '2025-05-20' },
      ],
    });
    expect(doc.stats.lastUpdatedAt.startsWith('2025-05-20')).toBe(true);
  });
});
