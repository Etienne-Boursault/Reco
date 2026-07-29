/**
 * tests/seo/test_robots_endpoint_cov.test.ts
 *
 * Complément de `test_robots.test.ts` : couvre la branche de repli de
 * `src/pages/robots.txt.ts` quand `Astro.site` n'est PAS configuré
 * (`site ?? new URL('http://localhost/')`) — cas d'un fork qui n'a pas
 * renseigné `SITE_URL`. Vérifie aussi le jeu complet de directives
 * `Disallow` (contrat SEO : rien d'interne indexable).
 */

import { describe, it, expect } from 'vitest';
import { GET } from '../../src/pages/robots.txt.js';

/** Contexte sans `site` — reproduit un `astro.config.mjs` sans `site`. */
const noSiteContext = () => ({ site: undefined }) as Parameters<typeof GET>[0];

async function bodyOf(ctx: Parameters<typeof GET>[0]): Promise<string> {
  return await ((await GET(ctx)) as Response).text();
}

describe('robots.txt — fallback sans Astro.site', () => {
  it('retombe sur http://localhost pour le sitemap', async () => {
    const body = await bodyOf(noSiteContext());
    expect(body).toContain('Sitemap: http://localhost/sitemap-index.xml');
  });

  it('ne produit pas de double slash dans le sitemap de repli', async () => {
    const body = await bodyOf(noSiteContext());
    expect(body).not.toMatch(/localhost\/\/sitemap/);
  });

  it('reste un robots.txt valide même sans site (User-agent présent)', async () => {
    const res = (await GET(noSiteContext())) as Response;
    expect(res.headers.get('Content-Type')).toBe('text/plain; charset=utf-8');
    expect(await res.text()).toMatch(/^User-agent: \*/);
  });
});

describe('robots.txt — jeu complet de Disallow', () => {
  const ctx = () => ({ site: new URL('https://reco.example/') }) as Parameters<typeof GET>[0];

  it('bloque toutes les routes internes attendues', async () => {
    const body = await bodyOf(ctx());
    for (const rule of [
      'Disallow: /*/verifier',
      'Disallow: /*/reports',
      'Disallow: /*/report/',
      'Disallow: /api/',
      'Disallow: /search.json',
      'Disallow: /recherche',
    ]) {
      expect(body).toContain(rule);
    }
  });

  it('se termine par une ligne vide (fin de fichier propre)', async () => {
    const body = await bodyOf(ctx());
    expect(body.endsWith('\n')).toBe(true);
  });
});
