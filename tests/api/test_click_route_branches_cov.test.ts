/**
 * tests/api/test_click_route_branches_cov.test.ts
 *
 * Complément de `test_click_route.test.ts` : couvre les branches par défaut
 * de `src/pages/api/click.ts` laissées de côté.
 *
 *  - POST sans en-tête `Content-Type` → `?? ''` (ligne 137), donc lecture
 *    via `request.text()` et non `request.json()`.
 *  - GET pixel sans aucun query param → `?? ''` sur url/cat/src (191-193) :
 *    le handler rejette (400 interne) mais le GIF est tout de même renvoyé.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const SELF = 'https://reco.example';

beforeEach(() => {
  const cwd = mkdtempSync(join(tmpdir(), 'reco-click-branch-'));
  process.env.TRACKING_IP_SALT = 'test-salt-for-tracking-branches-1234567890';
  process.env.RECO_QUIET = '1';
  vi.spyOn(process, 'cwd').mockReturnValue(cwd);
  vi.resetModules();
});

async function loadRoute() {
  const route = await import('../../src/pages/api/click.ts');
  const metrics = await import('../../src/lib/tracking/metrics.ts');
  metrics.resetClickMetrics();
  return { ...route, metrics };
}

function ctxFor(request: Request, clientAddress: string | null = '203.0.113.7') {
  return { request, url: new URL(request.url), clientAddress } as unknown as Parameters<
    Awaited<ReturnType<typeof loadRoute>>['POST']
  >[0];
}

describe('POST /api/click — Content-Type absent', () => {
  it('sans body ni Content-Type : lit text(), payload vide → 400', async () => {
    const route = await loadRoute();
    // `new Request(url, { method: 'POST' })` n'ajoute AUCUN content-type
    // (contrairement à un POST avec body string, qui force text/plain).
    const req = new Request(`${SELF}/api/click`, {
      method: 'POST',
      headers: { origin: SELF },
    });
    expect(req.headers.get('content-type')).toBeNull();

    const res = await route.POST(ctxFor(req));
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    // Zod rejette le payload vide (url manquante), pas un « json invalide ».
    expect(body.error).not.toMatch(/json invalide/);
    expect(route.metrics.getClickMetrics().byStatus['400']).toBe(1);
  });
});

describe('GET /api/click — query string vide', () => {
  it('sans url/cat/src : GIF renvoyé, 400 enregistré côté métrique', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const route = await loadRoute();
    const req = new Request(`${SELF}/api/click`, {
      method: 'GET',
      headers: { origin: SELF },
    });

    const res = await route.GET(ctxFor(req));
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toBe('image/gif');
    // Les trois `?? ''` produisent un payload vide → 400 côté handler.
    expect(route.metrics.getClickMetrics().byStatus['400']).toBe(1);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('sans reco/ref/bot_trap : les clés optionnelles ne sont pas ajoutées', async () => {
    const route = await loadRoute();
    const url = new URL(`${SELF}/api/click`);
    url.searchParams.set('url', 'https://themoviedb.org/movie/42');
    url.searchParams.set('cat', 'tmdb');
    url.searchParams.set('src', 'un-bon-moment');
    const req = new Request(url.toString(), { method: 'GET', headers: { origin: SELF } });

    const res = await route.GET(ctxFor(req));
    expect(res.status).toBe(200);
    // Payload valide sans recoId/ref/bot_trap → écriture acceptée (204 interne).
    expect(route.metrics.getClickMetrics().byStatus['204']).toBe(1);
  });
});
