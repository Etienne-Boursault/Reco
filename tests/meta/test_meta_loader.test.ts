/**
 * Tests du loader `meta-loader.ts`.
 */
import { describe, it, expect } from 'vitest';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  isMetaModeEnabled,
  loadMetaIndex,
} from '../../src/lib/registry/meta-loader.js';

function validIndex() {
  return {
    schemaVersion: 1,
    entries: [
      {
        sourceUrl: 'https://x/.well-known/reco-registry.json',
        registry: {
          schemaVersion: 1,
          siteUrl: 'https://x.example',
          podcast: { title: 'X', hosts: [], language: 'fr' },
          stats: {
            itemsCount: 1, mentionsCount: 2, episodesCount: 1, guestsCount: 1,
            lastUpdatedAt: '2026-06-12T00:00:00Z',
          },
          meta: { generator: 'Reco/0.3.0', generatedAt: '2026-06-12T00:00:00Z' },
          endpoints: {},
        },
      },
    ],
    totals: { podcasts: 1, items: 1, mentions: 2, episodes: 1, guests: 1 },
    generatedAt: '2026-06-12T00:00:00Z',
  };
}

describe('isMetaModeEnabled', () => {
  it('true ssi META_MODE=1', () => {
    expect(isMetaModeEnabled({ META_MODE: '1' })).toBe(true);
    expect(isMetaModeEnabled({})).toBe(false);
    expect(isMetaModeEnabled({ META_MODE: '0' })).toBe(false);
    expect(isMetaModeEnabled({ META_MODE: 'true' })).toBe(false);
  });
});

describe('loadMetaIndex', () => {
  it('renvoie null si META_MODE désactivé', () => {
    const dir = mkdtempSync(join(tmpdir(), 'reco-meta-'));
    const p = join(dir, 'meta_index.json');
    writeFileSync(p, JSON.stringify(validIndex()), 'utf-8');
    try {
      expect(loadMetaIndex(p, {})).toBeNull();
    } finally {
      rmSync(dir, { recursive: true });
    }
  });

  it('renvoie null si le fichier n’existe pas', () => {
    expect(loadMetaIndex('/nonexistent/x.json', { META_MODE: '1' })).toBeNull();
  });

  it('parse + retourne les entries quand activé', () => {
    const dir = mkdtempSync(join(tmpdir(), 'reco-meta-'));
    const p = join(dir, 'meta_index.json');
    writeFileSync(p, JSON.stringify(validIndex()), 'utf-8');
    try {
      const idx = loadMetaIndex(p, { META_MODE: '1' });
      expect(idx).not.toBeNull();
      expect(idx?.entries).toHaveLength(1);
      expect(idx?.entries[0].registry.podcast.title).toBe('X');
      expect(idx?.totals.podcasts).toBe(1);
    } finally {
      rmSync(dir, { recursive: true });
    }
  });

  it('renvoie null sur JSON cassé', () => {
    const dir = mkdtempSync(join(tmpdir(), 'reco-meta-'));
    const p = join(dir, 'meta_index.json');
    writeFileSync(p, '{not json', 'utf-8');
    try {
      expect(loadMetaIndex(p, { META_MODE: '1' })).toBeNull();
    } finally {
      rmSync(dir, { recursive: true });
    }
  });

  it('applique des totals par défaut si absents', () => {
    const dir = mkdtempSync(join(tmpdir(), 'reco-meta-'));
    const p = join(dir, 'meta_index.json');
    const data = validIndex() as Record<string, unknown>;
    delete data.totals;
    writeFileSync(p, JSON.stringify(data), 'utf-8');
    try {
      const idx = loadMetaIndex(p, { META_MODE: '1' });
      expect(idx?.totals.podcasts).toBe(1);
    } finally {
      rmSync(dir, { recursive: true });
    }
  });
});
