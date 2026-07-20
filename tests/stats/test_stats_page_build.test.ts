/**
 * Tests post-build des pages stats (`/stats` et `/[source]/stats`).
 *
 * Pré-requis : `npm run build` doit avoir été exécuté avant.
 *
 * Comportement CI vs local :
 *  - en local sans build, on skip silencieusement pour ne pas bloquer
 *    l'itération rapide.
 *  - en CI (`process.env.CI === 'true'`), on `expect.fail` explicitement.
 */
import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const DIST = join(process.cwd(), 'dist');
const globalStats = join(DIST, 'stats', 'index.html');
const hasBuild = existsSync(globalStats);

if (!hasBuild && process.env.CI === 'true') {
  describe('build output — stats (CI guard)', () => {
    it('dist/stats/index.html doit exister en CI', () => {
      expect.fail('Lancer `npm run build` avant les tests stats en CI.');
    });
  });
}

describe.skipIf(!hasBuild)('build output — /stats', () => {
  const html = readFileSync(globalStats, 'utf-8');

  it('contient le titre principal', () => {
    expect(html).toContain('Statistiques publiques');
  });

  it('embarque un JSON-LD Dataset', () => {
    expect(html).toMatch(/"@type"\s*:\s*"Dataset"/);
    expect(html).toContain('variableMeasured');
  });

  it('contient une table sémantique TopList', () => {
    expect(html).toContain('top-list');
    expect(html).toMatch(/<th[^>]*scope="col"/);
  });

  it('contient un chart SVG dans une <figure aria-labelledby> (M26-9)', () => {
    // Le libellé est porté par <figcaption> (SSOT a11y) et lié via
    // `aria-labelledby` sur la figure, pas par `aria-label` sur le SVG.
    expect(html).toMatch(/<figure[^>]*aria-labelledby="chart-/);
    expect(html).toMatch(/<figcaption[^>]*id="chart-/);
    expect(html).toMatch(/role="img"/);
  });

  it('contient les 5 compteurs principaux (cards)', () => {
    expect(html).toContain('podcasts indexés');
    expect(html).toContain('recommandations');
    expect(html).toContain('œuvres uniques');
    expect(html).toContain('invités uniques');
  });
});

describe.skipIf(!hasBuild)('build output — /[source]/stats', () => {
  // Trouve dynamiquement la 1re source ayant une page stats.
  const sourceDirs = (() => {
    if (!existsSync(DIST)) return [];
    return readdirSync(DIST).filter((d) =>
      existsSync(join(DIST, d, 'stats', 'index.html')),
    );
  })();

  it('génère au moins une page stats par source', () => {
    expect(sourceDirs.length).toBeGreaterThan(0);
  });

  it('contient un JSON-LD Dataset scopé', () => {
    if (sourceDirs.length === 0) return;
    const html = readFileSync(
      join(DIST, sourceDirs[0], 'stats', 'index.html'),
      'utf-8',
    );
    expect(html).toMatch(/"@type"\s*:\s*"Dataset"/);
    expect(html).toContain('Statistiques publiques');
  });
});
