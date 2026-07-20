/**
 * tests/tracking/test_settings.test.ts — TrackingSettings + categorizeUrl
 * (R-P1-13, R-P1-16, L25-27).
 */
import { describe, it, expect } from 'vitest';
import {
  TrackingSettings,
  DEFAULT_TRACKING_SETTINGS,
  fromSourceExtra,
  categorizeUrl,
} from '../../src/lib/tracking/settings.ts';

describe('fromSourceExtra', () => {
  it('retourne defaults si extra est null/undefined/non-objet', () => {
    expect(fromSourceExtra(null)).toBe(DEFAULT_TRACKING_SETTINGS);
    expect(fromSourceExtra(undefined)).toBe(DEFAULT_TRACKING_SETTINGS);
    expect(fromSourceExtra('lol')).toBe(DEFAULT_TRACKING_SETTINGS);
  });

  it('retourne defaults si extra.tracking absent', () => {
    expect(fromSourceExtra({})).toBe(DEFAULT_TRACKING_SETTINGS);
    expect(fromSourceExtra({ other: {} })).toBe(DEFAULT_TRACKING_SETTINGS);
  });

  it('overrides windowMs et maxHits', () => {
    const s = fromSourceExtra({ tracking: { windowMs: 30_000, maxHits: 10 } });
    expect(s.windowMs).toBe(30_000);
    expect(s.maxHits).toBe(10);
  });

  it('rejette les valeurs invalides (négatives, non-finite)', () => {
    const s = fromSourceExtra({
      tracking: { windowMs: -1, maxHits: Number.NaN },
    });
    expect(s.windowMs).toBe(60_000);
    expect(s.maxHits).toBe(60);
  });

  it('parse categoryOverrides + ignore catégories inconnues', () => {
    const s = fromSourceExtra({
      tracking: {
        categoryOverrides: {
          'partner.example': 'spotify',
          'bad.example': 'unknownCategory',
          '': 'tmdb',
        },
      },
    });
    expect(s.categoryOverrides['partner.example']).toBe('spotify');
    expect(s.categoryOverrides['bad.example']).toBeUndefined();
    expect(s.categoryOverrides['']).toBeUndefined();
  });

  it('expose un wrapper TrackingSettings', () => {
    expect(TrackingSettings.fromSourceExtra).toBe(fromSourceExtra);
    expect(TrackingSettings.DEFAULTS).toBe(DEFAULT_TRACKING_SETTINGS);
  });
});

describe('categorizeUrl', () => {
  it('mappe les hostnames connus', () => {
    expect(categorizeUrl('https://themoviedb.org/movie/42')).toBe('tmdb');
    expect(categorizeUrl('https://www.imdb.com/title/x')).toBe('imdb');
    expect(categorizeUrl('https://open.spotify.com/track/y')).toBe('spotify');
    expect(categorizeUrl('https://youtu.be/abc')).toBe('youtube');
    expect(categorizeUrl('https://m.youtube.com/watch?v=x')).toBe('youtube');
    expect(categorizeUrl('https://www.placedeslibraires.fr/livre/x')).toBe('library');
    expect(categorizeUrl('https://librairie-zorba.fr/x')).toBe('library');
  });

  it('renvoie other pour les URL inconnues', () => {
    expect(categorizeUrl('https://example.com/x')).toBe('other');
    expect(categorizeUrl('https://wikipedia.org/x')).toBe('other');
  });

  it('renvoie other sur URL invalide', () => {
    expect(categorizeUrl('not-a-url')).toBe('other');
    expect(categorizeUrl('')).toBe('other');
  });

  it('respecte les overrides (exact + sous-domaines)', () => {
    expect(categorizeUrl('https://partner.example/x', { 'partner.example': 'tmdb' })).toBe(
      'tmdb',
    );
    expect(
      categorizeUrl('https://cdn.partner.example/x', { 'partner.example': 'spotify' }),
    ).toBe('spotify');
  });
});
