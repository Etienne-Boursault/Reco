/**
 * Tests post-build SEO : vérifie que les pages générées dans `dist/` contiennent
 * bien les balises attendues (canonical, OG, JSON-LD optionnel, hreflang).
 *
 * Pré-requis : `npm run build` doit avoir été exécuté avant.
 *
 * Comportement CI vs local :
 *  - en local sans build, on skip silencieusement (`describe.skipIf`) pour
 *    laisser l'itération rapide possible ;
 *  - en CI (`process.env.CI === 'true'`), on **fail** explicitement si le
 *    build est absent — éviter un faux vert (CR senior M1).
 */

import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const DIST = join(process.cwd(), 'dist');
const indexPath = join(DIST, 'index.html');
const hasBuild = existsSync(indexPath);

if (!hasBuild && process.env.CI === 'true') {
  describe('build output — meta tags (CI guard)', () => {
    it('dist/index.html doit exister en CI (build préalable requis)', () => {
      expect.fail(
        `dist/index.html introuvable — exécute \`npm run build\` avant les tests SEO en CI.`,
      );
    });
  });
}

describe.skipIf(!hasBuild)('build output — meta tags', () => {
  const html = hasBuild ? readFileSync(indexPath, 'utf-8') : '';

  it('contient une balise canonical absolue', () => {
    expect(html).toMatch(/<link rel="canonical" href="https?:\/\/[^"]+"/);
  });

  it('contient og:site_name=Reco', () => {
    expect(html).toContain('property="og:site_name" content="Reco"');
  });

  it('contient hreflang fr et x-default', () => {
    expect(html).toContain('hreflang="fr"');
    expect(html).toContain('hreflang="x-default"');
  });

  it('contient og:image pointant vers une OG card générée (/og/...png)', () => {
    expect(html).toMatch(/property="og:image" content="[^"]*\/og\/[^"]+\.png"/);
  });

  it('contient twitter:card=summary_large_image', () => {
    expect(html).toContain('name="twitter:card" content="summary_large_image"');
  });

  it('contient og:locale fr_FR', () => {
    expect(html).toContain('property="og:locale" content="fr_FR"');
  });

  it('ne fuit pas reco.example en production (SITE_URL configuré)', () => {
    // Si SITE_URL était défini au build, aucune URL ne doit pointer vers
    // le placeholder de dev (`https://reco.example`).
    if (process.env.SITE_URL && !process.env.SITE_URL.includes('reco.example')) {
      expect(html).not.toContain('reco.example');
    }
  });

  it('og:image existe physiquement dans dist/og/', () => {
    // Anti-404 : cross-check que la carte OG référencée a bien été
    // générée par `getStaticPaths` (CR archi P1-A).
    const m = html.match(/property="og:image" content="[^"]*\/og\/([^"]+\.png)"/);
    if (!m) return; // pas d'og:image sur cette page, RAS.
    const ogPath = join(DIST, 'og', m[1]);
    expect(existsSync(ogPath), `og:image manquant : ${ogPath}`).toBe(true);
  });
});
