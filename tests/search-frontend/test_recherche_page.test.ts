/**
 * Tests post-build : vérifie que les artefacts existent dans `dist/` et
 * que l'index est conforme au format attendu.
 *
 * Skip silencieux si le build n'a pas été lancé (`dist/search.json` absent).
 */
import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { SEARCH_INDEX_VERSION, type SearchIndexFile } from '../../src/lib/search/types';

const dist = resolve(__dirname, '../../dist');
const indexPath = resolve(dist, 'search.json');
const recherchePath = resolve(dist, 'recherche/index.html');

const hasBuild = existsSync(indexPath);

describe.skipIf(!hasBuild)('dist/search.json — artefact build', () => {
  it('existe et reste sous 5 MB (critère de bascule ADR 0035)', () => {
    const size = statSync(indexPath).size;
    expect(size).toBeGreaterThan(100);
    expect(size).toBeLessThan(5 * 1024 * 1024);
  });

  it('a le bon format (version, count, docs[])', () => {
    const json = JSON.parse(readFileSync(indexPath, 'utf-8')) as SearchIndexFile;
    expect(json.version).toBe(SEARCH_INDEX_VERSION);
    expect(typeof json.generatedAt).toBe('string');
    expect(Array.isArray(json.docs)).toBe(true);
    expect(json.count).toBe(json.docs.length);
    expect(json.docs.length).toBeGreaterThan(0);
  });

  it('chaque doc a un id, kind, title, url', () => {
    const json = JSON.parse(readFileSync(indexPath, 'utf-8')) as SearchIndexFile;
    for (const d of json.docs.slice(0, 50)) {
      expect(d.id).toBeTruthy();
      expect(['item', 'episode', 'guest']).toContain(d.kind);
      expect(d.title).toBeTruthy();
      expect(d.url).toMatch(/^\//);
    }
  });
});

describe.skipIf(!existsSync(recherchePath))('dist/recherche/index.html — page publique', () => {
  it('contient le formulaire de recherche et le noindex', () => {
    const html = readFileSync(recherchePath, 'utf-8');
    expect(html).toMatch(/data-recherche-input/);
    expect(html).toMatch(/data-recherche-results/);
    expect(html).toMatch(/noindex/);
  });

  it('expose la palette Cmd+K', () => {
    const html = readFileSync(recherchePath, 'utf-8');
    expect(html).toMatch(/data-search-palette/);
  });
});
