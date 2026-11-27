/**
 * tests/api/test_click_route_pixel.test.ts — Endpoint `/api/click`, le pixel GET
 * de repli et l'origine derrière un proxy (SITE_URL).
 *
 * Coupé de `test_click_route.test.ts` (tour 1 de revue, PR #224 : fichiers de
 * 500 lignes au plus) ; montage dans `_click_aide.ts`.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SELF, ctxFor, installerLeCwd, loadRoute, makeRequest, validJsonBody } from './_click_aide';

beforeEach(installerLeCwd);

describe('GET /api/click (pixel)', () => {
  it('happy path → renvoie GIF 43 bytes', async () => {
    const route = await loadRoute();
    const req = makeRequest('GET', {
      headers: {
        origin: SELF,
      },
      query: {
        url: 'https://themoviedb.org/movie/42',
        cat: 'tmdb',
        src: 'un-bon-moment',
        reco: 'ubm-0001',
        ref: '/page',
      },
    });
    const res = await route.GET(ctxFor(req));
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toBe('image/gif');
    const buf = Buffer.from(await res.arrayBuffer());
    expect(res.headers.get('content-length')).toBe(String(buf.length));
    expect(buf.length).toBeGreaterThan(0);
    // GIF signature
    expect(buf.subarray(0, 3).toString('ascii')).toBe('GIF');
  });

  it('GET sans Origin mais Referer same-origin → 204 interne, GIF renvoyé', async () => {
    const route = await loadRoute();
    const req = makeRequest('GET', {
      headers: { referer: `${SELF}/some/page` },
      query: { url: 'https://x.example/', cat: 'other', src: 'src' },
    });
    const res = await route.GET(ctxFor(req));
    expect(res.status).toBe(200);
    const m = route.metrics.getClickMetrics();
    expect(m.byStatus['204']).toBe(1);
  });

  it('GET Origin invalide → 403 interne, GIF renvoyé quand même', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const route = await loadRoute();
    const req = makeRequest('GET', {
      headers: { origin: 'https://evil.example' },
      query: { url: 'https://x.example/', cat: 'other', src: 'src' },
    });
    const res = await route.GET(ctxFor(req));
    expect(res.status).toBe(200); // GIF toujours renvoyé
    const m = route.metrics.getClickMetrics();
    expect(m.byStatus['403']).toBe(1);
    warn.mockRestore();
  });

  it('GET payload invalide → 400 interne, GIF renvoyé, warn loggé', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const route = await loadRoute();
    const req = makeRequest('GET', {
      headers: { origin: SELF },
      query: { url: 'javascript:alert(1)', cat: 'other', src: 'src' },
    });
    const res = await route.GET(ctxFor(req));
    expect(res.status).toBe(200);
    expect(route.metrics.getClickMetrics().byStatus['400']).toBe(1);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('GET avec bot_trap → 204 silencieux', async () => {
    const route = await loadRoute();
    const req = makeRequest('GET', {
      headers: { origin: SELF },
      query: {
        url: 'https://x.example/',
        cat: 'other',
        src: 'src',
        bot_trap: 'pwn',
      },
    });
    const res = await route.GET(ctxFor(req));
    expect(res.status).toBe(200);
    expect(route.metrics.getClickMetrics().byStatus['204']).toBe(1);
  });

  it('GET IP null → toujours GIF, metric 204', async () => {
    const route = await loadRoute();
    const req = makeRequest('GET', {
      headers: { origin: SELF },
      query: { url: 'https://x.example/', cat: 'other', src: 'src' },
    });
    const res = await route.GET(ctxFor(req, null));
    expect(res.status).toBe(200);
    expect(route.metrics.getClickMetrics().byStatus['204']).toBe(1);
  });

  it('GET url > 2048 chars → warn + GIF + 400 interne', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const route = await loadRoute();
    const url = 'https://x.example/' + 'a'.repeat(3000);
    const req = makeRequest('GET', {
      headers: { origin: SELF },
      query: { url, cat: 'other', src: 'src' },
    });
    const res = await route.GET(ctxFor(req));
    expect(res.status).toBe(200);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe('derrière un proxy — l’origine attendue vient de SITE_URL', () => {
  // CE QUE CES TESTS PROTÈGENT
  //
  // L'hébergeur termine TLS devant l'application et lui parle en clair :
  // `request.url` porte donc `http://<hôte interne>`, quand le navigateur
  // annonce `Origin: https://unebonnere.co`. La comparaison échouait
  // toujours, et l'endpoint répondait 403 à CHAQUE clic — sans que rien ne
  // le signale, `sendBeacon` avalant l'erreur. Le tracking a paru
  // fonctionner pendant des semaines en n'enregistrant rien.
  //
  // Reproduit en local le 2026-08-25 : ajouter `X-Forwarded-Proto: https`
  // n'y changeait rien, `@astrojs/node` en mode middleware ne le lit pas.

  const SITE = new URL('https://unebonnere.co');

  function requeteDerriereProxy(origin: string) {
    // L'URL que voit le serveur : hôte interne, en clair.
    return new Request('http://10.0.0.4:3000/api/click', {
      method: 'POST',
      headers: { 'content-type': 'application/json', origin },
      body: validJsonBody(),
    });
  }

  it('accepte le domaine public alors que la requête arrive en clair', async () => {
    const route = await loadRoute();
    const res = await route.POST(
      ctxFor(requeteDerriereProxy('https://unebonnere.co'), '203.0.113.7', SITE),
    );

    expect(res.status).toBe(204);
  });

  it('refuse toujours une origine étrangère', async () => {
    // Le correctif ne doit pas désarmer la protection CSRF.
    const route = await loadRoute();
    const res = await route.POST(
      ctxFor(requeteDerriereProxy('https://pirate.example'), '203.0.113.7', SITE),
    );

    expect(res.status).toBe(403);
  });

  it('refuse le même domaine sur un autre protocole', async () => {
    const route = await loadRoute();
    const res = await route.POST(
      ctxFor(requeteDerriereProxy('http://unebonnere.co'), '203.0.113.7', SITE),
    );

    expect(res.status).toBe(403);
  });

  it('sans site configuré, retombe sur l’URL de la requête', async () => {
    // Développement et tests : pas de proxy, `request.url` est exact.
    const route = await loadRoute();
    const req = new Request('http://localhost:4321/api/click', {
      method: 'POST',
      headers: { 'content-type': 'application/json', origin: 'http://localhost:4321' },
      body: validJsonBody(),
    });
    const res = await route.POST(ctxFor(req));

    expect(res.status).toBe(204);
  });
});
