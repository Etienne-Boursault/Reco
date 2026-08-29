/**
 * tests/seo/test_jsonld_branches_cov.test.ts — Branches restantes des
 * factories JSON-LD : mapping créateur pour VideoGame / Person, champs
 * optionnels (url, description, publishedAt, rssUrl, podcastUrl).
 */
import { describe, it, expect } from 'vitest';
import {
  recoToSchema,
  episodeToSchema,
  sourceToPodcastSchema,
} from '../../src/lib/seo/jsonld.js';

describe('recoToSchema — mapping créateur par @type', () => {
  it("VideoGame : creator mappé sur 'publisher' (Organization)", () => {
    const s = recoToSchema({ type: 'jeu', title: 'Outer Wilds', author: 'Annapurna' });
    expect(s['@type']).toBe('VideoGame');
    expect(s.publisher).toEqual({ '@type': 'Organization', name: 'Annapurna' });
    expect(s.author).toBeUndefined();
    expect(s.creator).toBeUndefined();
  });

  it("Person (artiste) : aucun créateur tiers n'est posé", () => {
    const s = recoToSchema({ type: 'artiste', title: 'Chris Fleming', author: 'Someone' });
    expect(s['@type']).toBe('Person');
    expect(s.name).toBe('Chris Fleming');
    // L'œuvre EST la personne ⇒ ni author, ni creator, ni director.
    expect(s.author).toBeUndefined();
    expect(s.creator).toBeUndefined();
    expect(s.director).toBeUndefined();
    expect(Object.keys(s).sort()).toEqual(['@context', '@type', 'name']);
  });

  // `video` mappait sur VideoObject, qui exige `thumbnailUrl` + `uploadDate` :
  // on ne les a pas, et la Search Console remontait le balisage en erreur.
  // Le type est passé à CreativeWork, dont la propriété créateur est `creator`
  // (`director` reste couvert par Movie et TVSeries dans test_jsonld.test.ts).
  it("video → CreativeWork : creator mappé sur 'creator'", () => {
    const s = recoToSchema({ type: 'video', title: 'V', author: 'Réal' });
    expect(s['@type']).toBe('CreativeWork');
    expect(s.creator).toEqual({ '@type': 'Person', name: 'Réal' });
    expect(s.director).toBeUndefined();
  });

  it("MusicRecording : creator mappé sur 'byArtist'", () => {
    const s = recoToSchema({ type: 'musique', title: 'M', author: 'Artiste' });
    expect(s.byArtist).toEqual({ '@type': 'MusicGroup', name: 'Artiste' });
  });
});

describe('recoToSchema — champs optionnels', () => {
  it('url présente → posée ; absente → clé omise', () => {
    const withUrl = recoToSchema({ type: 'film', title: 'X', url: 'https://x.fr/f' });
    expect(withUrl.url).toBe('https://x.fr/f');
    expect('url' in recoToSchema({ type: 'film', title: 'X' })).toBe(false);
  });

  it('description présente → posée ; absente → clé omise', () => {
    const withDesc = recoToSchema({ type: 'film', title: 'X', description: 'Résumé' });
    expect(withDesc.description).toBe('Résumé');
    expect('description' in recoToSchema({ type: 'film', title: 'X' })).toBe(false);
  });
});

describe('episodeToSchema — champs optionnels', () => {
  const base = {
    guid: 'g1',
    title: 'Ep 1',
    url: 'https://x.fr/ep/1',
    podcastName: 'Un Bon Moment',
  };

  it('podcastUrl présent → url sur partOfSeries', () => {
    const s = episodeToSchema({ ...base, podcastUrl: 'https://x.fr/ubm' });
    expect(s.partOfSeries).toEqual({
      '@type': 'PodcastSeries',
      name: 'Un Bon Moment',
      url: 'https://x.fr/ubm',
    });
  });

  it('podcastUrl absent → partOfSeries sans url', () => {
    const series = episodeToSchema(base).partOfSeries as Record<string, unknown>;
    expect('url' in series).toBe(false);
  });

  it('description et publishedAt présents → posés', () => {
    const s = episodeToSchema({
      ...base,
      description: 'Résumé épisode',
      publishedAt: '2026-01-15',
    });
    expect(s.description).toBe('Résumé épisode');
    expect(s.datePublished).toBe('2026-01-15');
  });

  it('description et publishedAt absents → clés omises', () => {
    const s = episodeToSchema(base);
    expect('description' in s).toBe(false);
    expect('datePublished' in s).toBe(false);
  });
});

describe('sourceToPodcastSchema — champs optionnels', () => {
  const base = { id: 'ubm', title: 'Un Bon Moment', url: 'https://x.fr/ubm' };

  it('description et rssUrl présents → posés', () => {
    const s = sourceToPodcastSchema({
      ...base,
      description: 'Le podcast',
      rssUrl: 'https://x.fr/rss.xml',
    });
    expect(s.description).toBe('Le podcast');
    expect(s.webFeed).toBe('https://x.fr/rss.xml');
  });

  it('description et rssUrl absents → clés omises', () => {
    const s = sourceToPodcastSchema(base);
    expect('description' in s).toBe(false);
    expect('webFeed' in s).toBe(false);
  });
});
