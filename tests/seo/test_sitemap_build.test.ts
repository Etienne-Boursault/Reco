/**
 * Tests post-build : sitemap-index.xml + sitemap-0.xml produits par @astrojs/sitemap.
 *
 * Skip si dist/sitemap-index.xml absent (build préalable requis).
 * En CI (`process.env.CI === 'true'`), on fail au lieu de skip (CR senior M1).
 */

import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const DIST = join(process.cwd(), 'dist');
const indexPath = join(DIST, 'sitemap-index.xml');
const hasBuild = existsSync(indexPath);

if (!hasBuild && process.env.CI === 'true') {
  describe('sitemap (CI guard)', () => {
    it('dist/sitemap-index.xml doit exister en CI', () => {
      expect.fail('Build préalable requis pour les tests sitemap en CI.');
    });
  });
}

describe.skipIf(!hasBuild)('sitemap-index.xml', () => {
  const xml = hasBuild ? readFileSync(indexPath, 'utf-8') : '';

  it('contient au moins un <sitemap>', () => {
    expect(xml).toMatch(/<sitemap>/);
  });

  it('référence un sitemap-N.xml', () => {
    expect(xml).toMatch(/sitemap-\d+\.xml/);
  });
});

describe.skipIf(!hasBuild)('sitemap-0.xml', () => {
  const p = join(DIST, 'sitemap-0.xml');
  const xml = existsSync(p) ? readFileSync(p, 'utf-8') : '';

  it('contient au moins une URL', () => {
    expect(xml).toMatch(/<url>/);
    expect(xml).toMatch(/<loc>https?:\/\//);
  });

  it('exclut les pages /verifier', () => {
    expect(xml).not.toMatch(/\/verifier/);
  });

  it('exclut les images OG et endpoints (heuristique)', () => {
    expect(xml).not.toMatch(/\/og\/[^<]*\.png/);
  });

  it('contient lastmod (CR senior H5)', () => {
    expect(xml).toMatch(/<lastmod>/);
  });

  it('contient changefreq (CR senior H5)', () => {
    expect(xml).toMatch(/<changefreq>/);
  });
});
