/**
 * Tests des factories JSON-LD et de l'échappement XSS.
 */

import { describe, it, expect } from 'vitest';
import {
  safeJsonLd,
  recoToSchema,
  episodeToSchema,
  sourceToPodcastSchema,
  siteToWebsiteSchema,
  RECO_TYPE_TO_SCHEMA,
} from '../../src/lib/seo/jsonld.js';
import { siteConfig } from '../../src/config/site.js';

describe('safeJsonLd (anti-XSS)', () => {
  it("échappe </script> en \\u003c/script>", () => {
    const out = safeJsonLd({ payload: 'evil</script><script>alert(1)' });
    expect(out).not.toContain('</script>');
    expect(out).toContain('\\u003c/script');
  });

  it('produit un JSON re-parseable', () => {
    const data = { '@type': 'Movie', name: 'Test' };
    const out = safeJsonLd(data);
    // L'échappement < est décodé naturellement par JSON.parse.
    expect(JSON.parse(out)).toEqual(data);
  });

  it('échappe tous les < (pas seulement </script>)', () => {
    const out = safeJsonLd({ x: '<img src=x>' });
    expect(out).not.toMatch(/[^\\]</);
  });
});

describe('recoToSchema', () => {
  it('mappe film → Movie', () => {
    const s = recoToSchema({ type: 'film', title: 'Inception' });
    expect(s['@type']).toBe('Movie');
    expect(s.name).toBe('Inception');
  });

  it('mappe livre → Book', () => {
    expect(recoToSchema({ type: 'livre', title: 'X' })['@type']).toBe('Book');
  });

  it('mappe album → MusicAlbum', () => {
    expect(recoToSchema({ type: 'album', title: 'X' })['@type']).toBe('MusicAlbum');
  });

  it('type inconnu → CreativeWork', () => {
    expect(recoToSchema({ type: 'wtf', title: 'X' })['@type']).toBe('CreativeWork');
  });

  it("H11-2 — Movie : creator mappé sur 'director' (schema.org conform)", () => {
    const s = recoToSchema({ type: 'film', title: 'X', author: 'Nolan' });
    expect(s.author).toBeUndefined();
    expect(s.director).toEqual({ '@type': 'Person', name: 'Nolan' });
  });

  it("H11-2 — TVSeries : creator mappé sur 'director'", () => {
    const s = recoToSchema({ type: 'serie', title: 'X', author: 'Lynch' });
    expect(s.director).toEqual({ '@type': 'Person', name: 'Lynch' });
  });

  it("H11-2 — Book : creator mappé sur 'author'", () => {
    const s = recoToSchema({ type: 'livre', title: 'X', author: 'Camus' });
    expect(s.author).toEqual({ '@type': 'Person', name: 'Camus' });
  });

  it("H11-2 — MusicAlbum : creator mappé sur 'byArtist' (MusicGroup)", () => {
    const s = recoToSchema({ type: 'album', title: 'X', author: 'Daft Punk' });
    expect(s.byArtist).toEqual({ '@type': 'MusicGroup', name: 'Daft Punk' });
  });

  it("H11-2 — type générique : creator mappé sur 'creator'", () => {
    const s = recoToSchema({ type: 'autre', title: 'X', author: 'Anon' });
    expect(s.creator).toEqual({ '@type': 'Person', name: 'Anon' });
  });

  it('RECO_TYPE_TO_SCHEMA couvre tous les types recoType', () => {
    const expected = [
      'film', 'serie', 'livre', 'bd', 'musique', 'album',
      'podcast', 'jeu', 'spectacle', 'lieu', 'artiste', 'video', 'autre',
    ];
    for (const t of expected) {
      expect(RECO_TYPE_TO_SCHEMA[t], `mapping manquant : ${t}`).toBeTruthy();
    }
  });
});

describe('episodeToSchema', () => {
  it('produit un PodcastEpisode avec partOfSeries', () => {
    const s = episodeToSchema({
      guid: 'abc',
      title: 'Ep 1',
      url: 'https://x.fr/ep/1',
      podcastName: 'Un Bon Moment',
    });
    expect(s['@type']).toBe('PodcastEpisode');
    expect(s.name).toBe('Ep 1');
    const series = s.partOfSeries as Record<string, unknown>;
    expect(series['@type']).toBe('PodcastSeries');
    expect(series.name).toBe('Un Bon Moment');
  });
});

describe('sourceToPodcastSchema', () => {
  it("ne se dit pas l'éditeur du podcast, et retombe sur la page du site", () => {
    const s = sourceToPodcastSchema({
      id: 'ubm',
      title: 'Un Bon Moment',
      url: 'https://x.fr/ubm',
    });
    expect(s['@type']).toBe('PodcastSeries');
    expect(s.url).toBe('https://x.fr/ubm');
    expect(s).not.toHaveProperty('publisher');
    expect(s).not.toHaveProperty('sameAs');
  });

  it('pointe vers la page officielle et les autres présences du podcast', () => {
    const s = sourceToPodcastSchema({
      id: 'ubm',
      title: 'Un Bon Moment',
      url: 'https://x.fr/',
      officialUrl: 'https://podcasts.apple.com/fr/podcast/x/id1',
      sameAs: ['https://www.youtube.com/@KyanKhojandi'],
      rssUrl: 'https://feed.x/rss',
      description: 'Desc',
    });
    expect(s.url).toBe('https://podcasts.apple.com/fr/podcast/x/id1');
    expect(s.sameAs).toEqual(['https://www.youtube.com/@KyanKhojandi']);
    expect(s.webFeed).toBe('https://feed.x/rss');
  });
});

describe('siteToWebsiteSchema', () => {
  it('nomme le site, ses autres noms et ses comptes officiels', () => {
    const w = siteToWebsiteSchema('https://unebonnere.co/', 'Un Bon Moment');
    expect(w['@type']).toBe('WebSite');
    expect(w.name).toBe(siteConfig.siteName);
    expect(w.url).toBe('https://unebonnere.co/');
    expect(w.alternateName).toEqual(siteConfig.alternateNames);
    expect(w.sameAs).toEqual((siteConfig.socials ?? []).map((s) => s.url));
    expect(w.about).toEqual({ '@type': 'PodcastSeries', name: 'Un Bon Moment' });
  });

  it("n'invente rien quand la configuration est vide", () => {
    const avant = { alternateNames: siteConfig.alternateNames, socials: siteConfig.socials };
    Object.assign(siteConfig, { alternateNames: undefined, socials: undefined });
    try {
      const w = siteToWebsiteSchema('https://x.fr/');
      expect(w).not.toHaveProperty('alternateName');
      expect(w).not.toHaveProperty('sameAs');
      expect(w).not.toHaveProperty('about');
    } finally {
      Object.assign(siteConfig, avant);
    }
  });
});
