/**
 * Montage partagé par `test_click_route.test.ts` et
 * `test_click_route_pixel.test.ts` (le fichier dépassait 500 lignes : coupé par
 * thème, tour 1 de revue, PR #224).
 *
 * `installerLeCwd` se passe à `beforeEach` dans chaque fichier : il redirige
 * `process.cwd` vers un dossier jetable AVANT l'import de la route.
 */
import { vi } from 'vitest';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const SELF = 'https://reco.example';
export let CWD: string;

// Le module endpoint instancie un JsonlClickStorage avec `process.cwd()` par
// défaut. On stub `process.cwd` AVANT d'importer le module pour rediriger
// les écritures dans un tmpdir isolé.
export function installerLeCwd() {
  CWD = mkdtempSync(join(tmpdir(), 'reco-click-route-'));
  process.env.TRACKING_IP_SALT = 'test-salt-for-tracking-route-1234567890';
  process.env.RECO_QUIET = '1';
  vi.spyOn(process, 'cwd').mockReturnValue(CWD);
  vi.resetModules();
}

export async function loadRoute() {
  const route = await import('../../src/pages/api/click.ts');
  // CRUCIAL : on importe metrics depuis le MÊME graphe de modules que la
  // route (après resetModules dans beforeEach). Sinon `recordClickStatus`
  // côté route et `getClickMetrics` côté test pointent vers des Map différentes.
  const metrics = await import('../../src/lib/tracking/metrics.ts');
  metrics.resetClickMetrics();
  return { ...route, metrics };
}

export function makeRequest(
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

export function ctxFor(
  request: Request,
  clientAddress: string | null = '203.0.113.7',
  site?: URL,
) {
  return {
    request,
    url: new URL(request.url),
    clientAddress,
    // Astro pose `site` depuis `astro.config.mjs` — donc depuis `SITE_URL`.
    // Les tests qui ne le passent pas vérifient le comportement de repli.
    site,
  } as unknown as Parameters<Awaited<ReturnType<typeof loadRoute>>['POST']>[0];
}

export function validJsonBody(over: Record<string, unknown> = {}) {
  return JSON.stringify({
    url: 'https://themoviedb.org/movie/42',
    category: 'tmdb',
    sourceId: 'un-bon-moment',
    recoId: 'ubm-0001',
    ref: '/un-bon-moment/episode/abc',
    ...over,
  });
}
