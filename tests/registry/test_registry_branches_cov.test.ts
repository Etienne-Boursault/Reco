/**
 * tests/registry/test_registry_branches_cov.test.ts — Branches restantes de
 * `src/lib/registry/{meta-loader,consumer,generator}.ts`.
 *
 * Complète `tests/meta/test_meta_loader.test.ts` (happy path) en couvrant :
 *  - `RECO_OUTPUT_DIR` + chemin par défaut,
 *  - entrée registry invalide (callback `onInvalid` + log),
 *  - `RECO_META_LOADER_STRICT=1` (throw au lieu de `null`),
 *  - erreur non-`Error` remontée par `readFileSync` (formatage `String(err)`),
 *  - `FileMetaIndexLoader` et ses arguments par défaut.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  loadMetaIndex,
  FileMetaIndexLoader,
} from '../../src/lib/registry/meta-loader.js';
import { slugFromSiteUrl } from '../../src/lib/registry/consumer.js';
import { buildRegistry } from '../../src/lib/registry/generator.js';

function validRegistry() {
  return {
    schemaVersion: 1,
    siteUrl: 'https://x.example',
    podcast: { title: 'X', hosts: [], language: 'fr' },
    stats: {
      itemsCount: 1,
      mentionsCount: 2,
      episodesCount: 1,
      guestsCount: 1,
      lastUpdatedAt: '2026-06-12T00:00:00Z',
    },
    meta: { generator: 'Reco/0.3.0', generatedAt: '2026-06-12T00:00:00Z' },
    endpoints: {},
  };
}

/** Écrit `<dir>/meta/meta_index.json` et renvoie le dossier racine. */
function writeOutputDir(payload: unknown): string {
  const root = mkdtempSync(join(tmpdir(), 'reco-metaout-'));
  mkdirSync(join(root, 'meta'), { recursive: true });
  writeFileSync(join(root, 'meta', 'meta_index.json'), JSON.stringify(payload), 'utf-8');
  return root;
}

describe('loadMetaIndex — résolution du chemin', () => {
  it('RECO_OUTPUT_DIR redéfinit la racine `tools/output`', () => {
    const root = writeOutputDir({
      entries: [{ sourceUrl: 'https://x/.well-known/r.json', registry: validRegistry() }],
    });
    try {
      const idx = loadMetaIndex(undefined, {
        META_MODE: '1',
        RECO_OUTPUT_DIR: root,
      });
      expect(idx?.entries).toHaveLength(1);
      expect(idx?.entries[0].slug).toBe('x.example');
    } finally {
      rmSync(root, { recursive: true });
    }
  });

  it('sans RECO_OUTPUT_DIR ni path → cwd/tools/output (fichier absent ici → null)', () => {
    // Le repo n'a pas de `tools/output/meta/meta_index.json` versionné : la
    // branche `join(process.cwd(), …)` est exercée et retombe sur `null`.
    expect(loadMetaIndex(undefined, { META_MODE: '1' })).toBeNull();
  });
});

describe('loadMetaIndex — contenu dégradé', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('`entries` absent → liste vide et totals dérivés', () => {
    const root = writeOutputDir({ generatedAt: '2026-06-12T00:00:00Z' });
    try {
      const idx = loadMetaIndex(undefined, { META_MODE: '1', RECO_OUTPUT_DIR: root });
      expect(idx?.entries).toEqual([]);
      expect(idx?.totals).toEqual({
        podcasts: 0,
        items: 0,
        mentions: 0,
        episodes: 0,
        guests: 0,
      });
      expect(idx?.generatedAt).toBe('2026-06-12T00:00:00Z');
    } finally {
      rmSync(root, { recursive: true });
    }
  });

  it('registry invalide → entrée ignorée + warning tracé', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const root = writeOutputDir({
      entries: [
        { sourceUrl: 'https://cassé/.well-known/r.json', registry: { schemaVersion: 1 } },
        { sourceUrl: 'https://ok/.well-known/r.json', registry: validRegistry() },
      ],
    });
    try {
      const idx = loadMetaIndex(undefined, { META_MODE: '1', RECO_OUTPUT_DIR: root });
      expect(idx?.entries).toHaveLength(1);
      expect(warn).toHaveBeenCalledOnce();
      expect(String(warn.mock.calls[0][0])).toContain('https://cassé/.well-known/r.json');
      expect(String(warn.mock.calls[0][0])).toContain('registry invalide ignoré');
    } finally {
      rmSync(root, { recursive: true });
    }
  });

  it('RECO_META_LOADER_STRICT=1 → throw avec le message d origine', () => {
    const root = mkdtempSync(join(tmpdir(), 'reco-metaout-'));
    const p = join(root, 'meta_index.json');
    writeFileSync(p, '{not json', 'utf-8');
    try {
      expect(() =>
        loadMetaIndex(p, { META_MODE: '1', RECO_META_LOADER_STRICT: '1' }),
      ).toThrow(/parse meta_index échoué/);
      // Le message d'origine (SyntaxError.message) est propagé.
      expect(() =>
        loadMetaIndex(p, { META_MODE: '1', RECO_META_LOADER_STRICT: '1' }),
      ).toThrow(/JSON/i);
    } finally {
      rmSync(root, { recursive: true });
    }
  });
});

describe('loadMetaIndex — erreur non-`Error` (formatage String(err))', () => {
  afterEach(() => {
    vi.doUnmock('node:fs');
    vi.resetModules();
    vi.restoreAllMocks();
  });

  async function importWithThrowingFs() {
    vi.resetModules();
    vi.doMock('node:fs', async (importOriginal) => {
      const actual = await importOriginal<typeof import('node:fs')>();
      return {
        ...actual,
        default: actual,
        existsSync: () => true,
        readFileSync: () => {
          // Valeur non-`Error` : c'est exactement ce que la branche
          // `String(err)` du loader est censée savoir formater.
          throw 'boom-non-error';
        },
      };
    });
    return import('../../src/lib/registry/meta-loader.js');
  }

  it('mode non strict → warning contenant la valeur brute, retourne null', async () => {
    const mod = await importWithThrowingFs();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(mod.loadMetaIndex('/peu-importe.json', { META_MODE: '1' })).toBeNull();
    expect(String(warn.mock.calls[0][0])).toContain('boom-non-error');
  });

  it('mode strict → throw contenant la valeur brute', async () => {
    const mod = await importWithThrowingFs();
    expect(() =>
      mod.loadMetaIndex('/peu-importe.json', {
        META_MODE: '1',
        RECO_META_LOADER_STRICT: '1',
      }),
    ).toThrow(/boom-non-error/);
  });
});

describe('FileMetaIndexLoader', () => {
  it('path + env explicites → délègue à loadMetaIndex', () => {
    const root = writeOutputDir({
      entries: [{ sourceUrl: 'https://x/.well-known/r.json', registry: validRegistry() }],
    });
    const p = join(root, 'meta', 'meta_index.json');
    try {
      const loader = new FileMetaIndexLoader(p, { META_MODE: '1' });
      expect(loader.load()?.entries).toHaveLength(1);
    } finally {
      rmSync(root, { recursive: true });
    }
  });

  it('arguments par défaut (META_INDEX_PATH + process.env)', () => {
    const saved = process.env.META_MODE;
    delete process.env.META_MODE;
    try {
      // META_MODE absent de process.env ⇒ null, sans toucher au disque.
      expect(new FileMetaIndexLoader().load()).toBeNull();
    } finally {
      if (saved === undefined) delete process.env.META_MODE;
      else process.env.META_MODE = saved;
    }
  });
});

describe('slugFromSiteUrl — repli non-URL', () => {
  it('URL sans hostname (schéma file:) → repli sur la chaîne nettoyée', () => {
    expect(slugFromSiteUrl('file:///tmp/registry.json')).toBe('file-tmp-registry.json');
  });

  it("valeur nulle → 'unknown' (garde défensive `siteUrl ?? ''`)", () => {
    // La signature annonce `string`, mais le loader consomme du JSON non
    // validé : la garde `String(siteUrl ?? '')` est bien atteignable en prod.
    expect(slugFromSiteUrl(null as unknown as string)).toBe('unknown');
    expect(slugFromSiteUrl(undefined as unknown as string)).toBe('unknown');
  });
});

describe('buildRegistry — branches restantes', () => {
  const base = {
    source: { id: 'ubm', title: 'Un Bon Moment' },
    episodes: [],
    mentions: [],
    items: [],
    siteUrl: 'https://ubm.example',
    generator: 'Reco/0.3.0',
    generatedAt: '2026-07-01T00:00:00.000Z',
  };

  it('source sans `hosts` → tableau vide dans le document', () => {
    const doc = buildRegistry(base);
    expect(doc.podcast.hosts).toEqual([]);
    expect(doc.stats.guestsCount).toBe(0);
  });

  it('episode.date déjà un objet Date → utilisé tel quel', () => {
    const doc = buildRegistry({
      ...base,
      episodes: [{ guid: 'e1', sourceId: 'ubm', date: new Date('2026-03-15T00:00:00Z') }],
    });
    expect(doc.stats.lastUpdatedAt).toBe('2026-03-15T00:00:00.000Z');
  });

  it('garde le max quand un épisode plus ancien suit un plus récent', () => {
    const doc = buildRegistry({
      ...base,
      episodes: [
        { guid: 'e1', sourceId: 'ubm', date: new Date('2026-03-15T00:00:00Z') },
        { guid: 'e2', sourceId: 'ubm', date: new Date('2025-01-01T00:00:00Z') },
      ],
    });
    expect(doc.stats.lastUpdatedAt).toBe('2026-03-15T00:00:00.000Z');
  });

  it('épisode sans date → ignoré pour lastUpdatedAt', () => {
    const doc = buildRegistry({
      ...base,
      episodes: [{ guid: 'e1', sourceId: 'ubm' }],
    });
    expect(doc.stats.lastUpdatedAt).toBe(base.generatedAt);
  });
});
