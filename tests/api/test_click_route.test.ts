/**
 * tests/api/test_click_route.test.ts — Endpoint `/api/click` (route Astro).
 *
 * Tests d'intégration du fichier `src/pages/api/click.ts` couvrant :
 *  - POST happy path (JSON + text/plain sendBeacon)
 *  - POST body trop volumineux (Content-Length > 8 KiB) → 413
 *  - POST body chunked sans Content-Length, lu > 8 KiB → 413
 *  - POST sans Origin → 403
 *  - POST JSON invalide → 400
 *  - POST Sec-GPC = '1' → 204
 *  - POST url > 2048 chars : warn et 400
 *  - POST IP indéterminable → 204
 *  - POST avec proxy trusted (X-Forwarded-For)
 *  - GET pixel happy path, payload valide
 *  - GET pixel sans Origin (Referer fallback)
 *  - GET pixel avec query params optionnels (reco, ref, bot_trap)
 *  - GET pixel IP null → toujours renvoie le GIF
 *  - GET pixel avec URL trop longue → 400 mais GIF retourné
 *
 * Les cas GET (pixel) et l'origine derrière un proxy sont dans
 * `test_click_route_pixel.test.ts` (fichier coupé, tour 1 de revue, PR #224) ;
 * montage partagé dans `_click_aide.ts`.
 *
 * Cible : 100 % de coverage sur src/pages/api/click.ts.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { CWD, SELF, ctxFor, installerLeCwd, loadRoute, makeRequest, validJsonBody } from './_click_aide';

beforeEach(installerLeCwd);

describe('POST /api/click', () => {
  it('happy path JSON → 204', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: {
        'content-type': 'application/json',
        origin: SELF,
      },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(204);
  });

  it('text/plain (sendBeacon) → 204', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: {
        'content-type': 'text/plain;charset=UTF-8',
        origin: SELF,
      },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(204);
  });

  it('B-HIGH-1 Content-Length > 8 KiB → 413', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: 'x',
      headers: {
        'content-type': 'application/json',
        origin: SELF,
        'content-length': String(9 * 1024),
      },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(413);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/body/);
  });

  it('B-HIGH-1 body chunked > 8 KiB (sans Content-Length) → 413', async () => {
    const route = await loadRoute();
    // text/plain → POST handler lit text() puis check byteLength
    const big = JSON.stringify({ x: 'a'.repeat(9000) });
    const req = makeRequest('POST', {
      body: big,
      headers: {
        'content-type': 'text/plain',
        origin: SELF,
      },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(413);
  });

  it('Origin absent → 403', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: { 'content-type': 'application/json' },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(403);
  });

  it('JSON invalide → 400', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: '{not-json',
      headers: {
        'content-type': 'application/json',
        origin: SELF,
      },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toMatch(/json/);
  });

  it('Sec-GPC = 1 → 204', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: {
        'content-type': 'application/json',
        origin: SELF,
        'sec-gpc': '1',
      },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(204);
  });

  it('DNT = 1 : 204 sans écriture, DNT absent : la ligne est écrite avec les trois oui/non (D1)', async () => {
    const route = await loadRoute();
    const { listDailyFiles, readDailyEvents } = await import('../../src/lib/tracking/storage.ts');
    const envoyer = (headers: Record<string, string>) =>
      route.POST(
        ctxFor(
          makeRequest('POST', {
            body: validJsonBody({ revenant: false, aVuEpisode: true, aVuFiche: true }),
            headers: { 'content-type': 'application/json', origin: SELF, ...headers },
          }),
        ),
      );
    expect((await envoyer({ dnt: '1' })).status).toBe(204);
    expect(listDailyFiles('un-bon-moment', CWD)).toHaveLength(0);
    expect((await envoyer({})).status).toBe(204);
    const lignes = listDailyFiles('un-bon-moment', CWD).flatMap(readDailyEvents);
    expect(lignes).toHaveLength(1);
    expect(lignes[0]).toMatchObject({ revenant: false, aVuEpisode: true, aVuFiche: true });
  });

  it('GET pixel avec DNT = 1 : GIF renvoyé, aucune écriture (D1)', async () => {
    const route = await loadRoute();
    const { listDailyFiles } = await import('../../src/lib/tracking/storage.ts');
    const res = await route.GET(
      ctxFor(
        makeRequest('GET', {
          headers: { origin: SELF, dnt: '1' },
          query: { url: 'https://themoviedb.org/movie/42', cat: 'tmdb', src: 'un-bon-moment' },
        }),
      ),
    );
    expect(res.status).toBe(200);
    expect(listDailyFiles('un-bon-moment', CWD)).toHaveLength(0);
  });

  it('URL > 2048 chars : warn + 400 (validator reject)', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const route = await loadRoute();
    const url = 'https://x.example/' + 'a'.repeat(3000);
    const req = makeRequest('POST', {
      body: JSON.stringify({
        url,
        category: 'other',
        sourceId: 'src',
      }),
      headers: {
        'content-type': 'application/json',
        origin: SELF,
      },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(400);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('clientAddress indéterminable → 204 silencieux', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: {
        'content-type': 'application/json',
        origin: SELF,
      },
    });
    const res = await route.POST(ctxFor(req, null));
    expect(res.status).toBe(204);
  });

  it('clientAddress throw (Astro prerender) → 204', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: {
        'content-type': 'application/json',
        origin: SELF,
      },
    });
    const ctx = {
      request: req,
      url: new URL(req.url),
      get clientAddress(): string {
        throw new Error('cannot access clientAddress');
      },
    } as unknown as Parameters<typeof route.POST>[0];
    const res = await route.POST(ctx);
    expect(res.status).toBe(204);
  });

  it('proxy trusted + X-Forwarded-For → utilise first hop', async () => {
    process.env.TRUSTED_PROXIES = '10.0.0.1';
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: {
        'content-type': 'application/json',
        origin: SELF,
        'x-forwarded-for': '203.0.113.99, 10.0.0.1',
      },
    });
    const res = await route.POST(ctxFor(req, '10.0.0.1'));
    expect(res.status).toBe(204);
    delete process.env.TRUSTED_PROXIES;
  });

  it('proxy trusted sans X-Forwarded-For → fallback clientAddress', async () => {
    process.env.TRUSTED_PROXIES = '10.0.0.1';
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: {
        'content-type': 'application/json',
        origin: SELF,
      },
    });
    const res = await route.POST(ctxFor(req, '10.0.0.1'));
    expect(res.status).toBe(204);
    delete process.env.TRUSTED_PROXIES;
  });

  it('proxy trusted + X-Forwarded-For vide string → fallback clientAddress', async () => {
    process.env.TRUSTED_PROXIES = '10.0.0.1';
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: {
        'content-type': 'application/json',
        origin: SELF,
        'x-forwarded-for': ' , 10.0.0.1',
      },
    });
    const res = await route.POST(ctxFor(req, '10.0.0.1'));
    expect(res.status).toBe(204);
    delete process.env.TRUSTED_PROXIES;
  });

  it('empty body text/plain → payload {} → 400 validator', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: '',
      headers: {
        'content-type': 'text/plain',
        origin: SELF,
      },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(400);
  });

  it('Content-Length invalide (non-numérique) → ignore borne', async () => {
    const route = await loadRoute();
    const req = makeRequest('POST', {
      body: validJsonBody(),
      headers: {
        'content-type': 'application/json',
        origin: SELF,
        'content-length': 'abc',
      },
    });
    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(204);
  });
});
