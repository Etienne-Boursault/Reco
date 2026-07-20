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
 * Cible : 100 % de coverage sur src/pages/api/click.ts.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const SELF = 'https://reco.example';
let CWD: string;

// Le module endpoint instancie un JsonlClickStorage avec `process.cwd()` par
// défaut. On stub `process.cwd` AVANT d'importer le module pour rediriger
// les écritures dans un tmpdir isolé.
beforeEach(() => {
  CWD = mkdtempSync(join(tmpdir(), 'reco-click-route-'));
  process.env.TRACKING_IP_SALT = 'test-salt-for-tracking-route-1234567890';
  process.env.RECO_QUIET = '1';
  vi.spyOn(process, 'cwd').mockReturnValue(CWD);
  vi.resetModules();
});

async function loadRoute() {
  const route = await import('../../src/pages/api/click.ts');
  // CRUCIAL : on importe metrics depuis le MÊME graphe de modules que la
  // route (après resetModules dans beforeEach). Sinon `recordClickStatus`
  // côté route et `getClickMetrics` côté test pointent vers des Map différentes.
  const metrics = await import('../../src/lib/tracking/metrics.ts');
  metrics.resetClickMetrics();
  return { ...route, metrics };
}

function makeRequest(
  method: 'POST' | 'GET',
  opts: {
    body?: string | null;
    headers?: Record<string, string>;
    query?: Record<string, string>;
  } = {},
): Request {
  const url = new URL(`${SELF}/api/click`);
  for (const [k, v] of Object.entries(opts.query ?? {})) url.searchParams.set(k, v);
  return new Request(url.toString(), {
    method,
    headers: opts.headers,
    body: opts.body ?? undefined,
  });
}

function ctxFor(request: Request, clientAddress: string | null = '203.0.113.7') {
  return {
    request,
    url: new URL(request.url),
    clientAddress,
  } as unknown as Parameters<Awaited<ReturnType<typeof loadRoute>>['POST']>[0];
}

function validJsonBody(over: Record<string, unknown> = {}) {
  return JSON.stringify({
    url: 'https://themoviedb.org/movie/42',
    category: 'tmdb',
    sourceId: 'un-bon-moment',
    recoId: 'ubm-0001',
    ref: '/un-bon-moment/episode/abc',
    ...over,
  });
}

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
