/**
 * Tests robots.txt — endpoint Astro dynamique.
 */

import { describe, it, expect } from 'vitest';
import { GET } from '../../src/pages/robots.txt.js';

const fakeContext = (siteUrl: string) =>
  ({ site: new URL(siteUrl) }) as Parameters<typeof GET>[0];

describe('robots.txt endpoint', () => {
  it('retourne text/plain UTF-8', async () => {
    const res = await GET(fakeContext('https://example.com'));
    expect(res.headers.get('Content-Type')).toMatch(/text\/plain/);
  });

  it('contient User-agent: *', async () => {
    const body = await (await GET(fakeContext('https://example.com'))).text();
    expect(body).toMatch(/User-agent:\s*\*/);
  });

  it("n'émet PAS Allow: / (redondant, défaut robots.txt)", async () => {
    const body = await (await GET(fakeContext('https://example.com'))).text();
    expect(body).not.toMatch(/^Allow:\s*\//m);
  });

  it('interdit /*\/verifier (pages de relecture interne)', async () => {
    const body = await (await GET(fakeContext('https://example.com'))).text();
    expect(body).toContain('Disallow: /*/verifier');
  });

  it('pointe vers le sitemap-index absolu basé sur Astro.site', async () => {
    const body = await (await GET(fakeContext('https://reco.example/'))).text();
    expect(body).toContain('Sitemap: https://reco.example/sitemap-index.xml');
  });

  it('strip le trailing slash de la base', async () => {
    const body = await (await GET(fakeContext('https://x.test/'))).text();
    // Pas de double slash dans l'URL sitemap.
    expect(body).not.toMatch(/x\.test\/\/sitemap/);
  });
});
