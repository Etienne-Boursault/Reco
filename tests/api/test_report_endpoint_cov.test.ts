/**
 * tests/api/test_report_endpoint_cov.test.ts
 *
 * Endpoint `/api/report` (`src/pages/api/report.ts`).
 *
 * Le shim Astro fait quatre choses : parser le `FormData`, résoudre l'IP
 * (avec la garde `TRUSTED_PROXIES`, H16-6), déléguer à `handleReport`, puis
 * — sur signalement accepté — enrichir le ping Matrix via `buildReportContext`.
 *
 * Frontières mockées :
 *  - `astro:content` (collections) ;
 *  - `src/lib/reports/notify` (réseau Matrix) — on l'espionne aussi pour
 *    observer le contexte enrichi, seul moyen de tester `buildReportContext`.
 *
 * Les écritures disque de `writeReport` sont redirigées vers un tmpdir via
 * un stub de `process.cwd`.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const getCollection = vi.fn();
const notifyReportMatrix = vi.fn(async () => {});

vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

vi.mock('../../src/lib/reports/notify.js', () => ({
  notifyReportMatrix: (...args: unknown[]) => notifyReportMatrix(...(args as [])),
}));

const SELF = 'https://reco.example';

interface Entry {
  id?: string;
  data: Record<string, unknown>;
}

function collections(map: Record<string, Entry[]>): void {
  getCollection.mockImplementation(async (name: string) => map[name] ?? []);
}

type Route = typeof import('../../src/pages/api/report.js');

/**
 * Recharge la route dans un graphe de modules neuf : indispensable pour que
 * `defaultRateLimiter` (1 report / 5 min / IP) et le cache anti-rejeu des
 * jti repartent de zéro entre les tests.
 */
async function loadRoute(): Promise<Route & { makeChallenge: () => { token: string; answer: string } }> {
  vi.resetModules();
  const route = (await import('../../src/pages/api/report.js')) as unknown as Route;
  const captcha = await import('../../src/lib/reports/captcha.js');
  return {
    ...route,
    makeChallenge() {
      const c = captcha.generateChallenge();
      const m = /(\d) \+ (\d)/.exec(c.question);
      if (!m) throw new Error(`question captcha inattendue: ${c.question}`);
      return { token: c.token, answer: String(Number(m[1]) + Number(m[2])) };
    },
  };
}

function formRequest(
  fields: Record<string, string | Blob>,
  headers: Record<string, string> = { origin: SELF },
): Request {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.append(k, v as string);
  return new Request(`${SELF}/api/report`, { method: 'POST', body: fd, headers });
}

function ctxFor(request: Request, clientAddress: string | null = '203.0.113.42') {
  return { request, clientAddress } as unknown as Parameters<Route['POST']>[0];
}

const SAVED_SSR = process.env.RECO_SSR;
const SAVED_PROXIES = process.env.TRUSTED_PROXIES;

beforeEach(() => {
  getCollection.mockReset();
  collections({ recos: [], episodes: [] });
  notifyReportMatrix.mockClear();
  process.env.RECO_QUIET = '1';
  delete process.env.TRUSTED_PROXIES;
  vi.spyOn(process, 'cwd').mockReturnValue(mkdtempSync(join(tmpdir(), 'reco-report-route-')));
});

afterEach(() => {
  vi.restoreAllMocks();
  if (SAVED_SSR === undefined) delete process.env.RECO_SSR;
  else process.env.RECO_SSR = SAVED_SSR;
  if (SAVED_PROXIES === undefined) delete process.env.TRUSTED_PROXIES;
  else process.env.TRUSTED_PROXIES = SAVED_PROXIES;
});

/** Champs d'un signalement valide, captcha frais inclus. */
function validFields(challenge: { token: string; answer: string }): Record<string, string> {
  return {
    sourceId: 'un-bon-moment',
    recoId: 'ubm-0001',
    category: 'broken-link',
    details: 'Le lien vers le film ne fonctionne plus depuis hier.',
    captchaToken: challenge.token,
    captchaAnswer: challenge.answer,
  };
}

describe('GET /api/report', () => {
  it('renvoie 405 avec Allow: POST', async () => {
    const { GET } = await loadRoute();
    const res = (await GET({} as never)) as Response;

    expect(res.status).toBe(405);
    expect(res.headers.get('Allow')).toBe('POST');
    expect(res.headers.get('Content-Type')).toBe('application/json; charset=utf-8');
    expect(await res.json()).toEqual({ success: false, error: 'method not allowed' });
  });
});

describe('prerender (SSR opt-in)', () => {
  it('vaut true sans RECO_SSR (build statique du kit)', async () => {
    delete process.env.RECO_SSR;
    const mod = await loadRoute();
    expect(mod.prerender).toBe(true);
  });

  it('vaut false avec RECO_SSR=1 (adaptateur Node présent)', async () => {
    process.env.RECO_SSR = '1';
    const mod = await loadRoute();
    expect(mod.prerender).toBe(false);
  });
});

describe('POST /api/report — parsing du FormData', () => {
  it('accepte un signalement valide et renvoie son id', async () => {
    const route = await loadRoute();
    const res = (await route.POST(ctxFor(formRequest(validFields(route.makeChallenge()))))) as Response;
    const body = (await res.json()) as { success: boolean; id: string };

    expect(res.status).toBe(200);
    expect(body.success).toBe(true);
    expect(body.id).toMatch(/^rep-/);
  });

  it('ignore les entrées non scalaires (fichier joint)', async () => {
    const route = await loadRoute();
    const fields: Record<string, string | Blob> = {
      ...validFields(route.makeChallenge()),
      // Un `File` glissé dans le form ne doit ni casser le parsing ni être
      // transmis à Zod (qui est en `.strict()` et rejetterait la clé).
      piece_jointe: new Blob(['coucou'], { type: 'text/plain' }),
    };
    const res = (await route.POST(ctxFor(formRequest(fields)))) as Response;

    expect(res.status).toBe(200);
  });

  it('rejette 403 quand ni Origin ni Referer ne sont présents', async () => {
    const route = await loadRoute();
    const req = formRequest(validFields(route.makeChallenge()), {});
    const res = (await route.POST(ctxFor(req))) as Response;

    expect(res.status).toBe(403);
    expect((await res.json()) as unknown).toMatchObject({ success: false });
  });

  it('utilise Referer en repli quand Origin est absent', async () => {
    const route = await loadRoute();
    const req = formRequest(validFields(route.makeChallenge()), {
      referer: `${SELF}/un-bon-moment/report/ubm-0001`,
    });
    const res = (await route.POST(ctxFor(req))) as Response;

    expect(res.status).toBe(200);
  });

  it('rejette 400 sur payload invalide (détails trop courts)', async () => {
    const route = await loadRoute();
    const fields = { ...validFields(route.makeChallenge()), details: 'ko' };
    const res = (await route.POST(ctxFor(formRequest(fields)))) as Response;
    const body = (await res.json()) as { success: boolean; error: string };

    expect(res.status).toBe(400);
    expect(body.success).toBe(false);
    expect(body.error).toMatch(/details/);
  });

  it('répond 204 silencieux quand le honeypot est rempli', async () => {
    const route = await loadRoute();
    const fields = { ...validFields(route.makeChallenge()), url_unused: 'https://spam.example' };
    const res = (await route.POST(ctxFor(formRequest(fields)))) as Response;

    expect(res.status).toBe(204);
    // Un 204 ne peut pas porter de body (spec Fetch) — cf. bug corrigé.
    expect(res.body).toBeNull();
    // Aucun ping Matrix sur une soumission non acceptée.
    expect(notifyReportMatrix).not.toHaveBeenCalled();
  });
});

describe('POST /api/report — résolution de l’IP (H16-6)', () => {
  it("utilise clientAddress quand aucun proxy n'est déclaré trusted", async () => {
    const route = await loadRoute();
    const req = formRequest(validFields(route.makeChallenge()), {
      origin: SELF,
      'x-forwarded-for': '198.51.100.9',
    });
    // XFF présent mais proxy non trusted → il doit être IGNORÉ. On le prouve
    // en re-soumettant depuis la même IP directe : le rate-limit doit taper.
    expect(((await route.POST(ctxFor(req, '10.0.0.1'))) as Response).status).toBe(200);

    const req2 = formRequest(validFields(route.makeChallenge()), {
      origin: SELF,
      'x-forwarded-for': '198.51.100.77',
    });
    const res2 = (await route.POST(ctxFor(req2, '10.0.0.1'))) as Response;
    expect(res2.status).toBe(429);
  });

  it('fait confiance à X-Forwarded-For derrière un proxy déclaré', async () => {
    process.env.TRUSTED_PROXIES = '10.0.0.1, 10.0.0.2';
    const route = await loadRoute();
    const mk = (xff: string) =>
      formRequest(validFields(route.makeChallenge()), { origin: SELF, 'x-forwarded-for': xff });

    expect(((await route.POST(ctxFor(mk('198.51.100.9'), '10.0.0.1'))) as Response).status).toBe(200);
    // IP réelle différente derrière le même proxy → pas de rate-limit croisé.
    const res2 = (await route.POST(ctxFor(mk('198.51.100.77'), '10.0.0.1'))) as Response;
    expect(res2.status).toBe(200);
    // Même IP réelle → rate-limit.
    const res3 = (await route.POST(ctxFor(mk('198.51.100.77'), '10.0.0.1'))) as Response;
    expect(res3.status).toBe(429);
  });

  it('retombe sur clientAddress si X-Forwarded-For est vide après trim', async () => {
    process.env.TRUSTED_PROXIES = '10.0.0.1';
    const route = await loadRoute();
    const req = formRequest(validFields(route.makeChallenge()), {
      origin: SELF,
      'x-forwarded-for': ' , 198.51.100.9',
    });
    expect(((await route.POST(ctxFor(req, '10.0.0.1'))) as Response).status).toBe(200);

    // Le bucket de rate-limit est celui de `10.0.0.1` (fallback), pas du XFF.
    const req2 = formRequest(validFields(route.makeChallenge()), {
      origin: SELF,
      'x-forwarded-for': ' , 203.0.113.5',
    });
    expect(((await route.POST(ctxFor(req2, '10.0.0.1'))) as Response).status).toBe(429);
  });

  it('tolère un clientAddress qui lève (route pré-rendue)', async () => {
    const route = await loadRoute();
    const req = formRequest(validFields(route.makeChallenge()));
    const ctx = {
      request: req,
      get clientAddress(): string {
        throw new Error('clientAddress indisponible en static build');
      },
    } as unknown as Parameters<Route['POST']>[0];

    const res = (await route.POST(ctx)) as Response;
    expect(res.status).toBe(200);
  });

  it('retombe sur 0.0.0.0 quand clientAddress est null', async () => {
    const route = await loadRoute();
    const req = formRequest(validFields(route.makeChallenge()));
    expect(((await route.POST(ctxFor(req, null))) as Response).status).toBe(200);

    // Tous les clients sans IP partagent le bucket `0.0.0.0`.
    const req2 = formRequest(validFields(route.makeChallenge()));
    expect(((await route.POST(ctxFor(req2, null))) as Response).status).toBe(429);
  });
});

describe('POST /api/report — contexte du ping Matrix', () => {
  /** Reco complète + épisode correspondant. */
  function seedFull(): void {
    collections({
      recos: [
        {
          data: {
            id: 'ubm-0001',
            sourceId: { id: 'un-bon-moment' },
            episodeGuid: 'guid-42',
            title: 'Dune',
            types: ['film', 'inconnu-du-mapping'],
            recommendedBy: 'Bruno',
            timestamp: '01:42:03',
          },
        },
      ],
      episodes: [
        {
          data: {
            guid: 'guid-42',
            sourceId: { id: 'un-bon-moment' },
            title: 'Épisode avec Bruno',
            season: 5,
            number: 21,
          },
        },
      ],
    });
  }

  async function submit(): Promise<Response> {
    const route = await loadRoute();
    return (await route.POST(ctxFor(formRequest(validFields(route.makeChallenge()))))) as Response;
  }

  it('enrichit la notif avec titre, types, invité, timestamp, épisode et lien', async () => {
    seedFull();
    const res = await submit();
    expect(res.status).toBe(200);

    expect(notifyReportMatrix).toHaveBeenCalledTimes(1);
    const [report, opts] = notifyReportMatrix.mock.calls[0] as [
      { id: string },
      { context: Record<string, unknown> },
    ];
    expect(report.id).toMatch(/^rep-/);
    expect(opts.context).toEqual({
      recoTitle: 'Dune',
      // `TYPE_LABELS[typ] ?? typ` : le type inconnu est conservé tel quel.
      recoTypes: 'Film, inconnu-du-mapping',
      recommendedBy: 'Bruno',
      timestamp: '01:42:03',
      episodeLabel: 'S5·E21',
      episodeTitle: 'Épisode avec Bruno',
      url: `${SELF}/un-bon-moment/episode/guid-42`,
    });
  });

  it('laisse les champs optionnels indéfinis quand la reco est dépouillée', async () => {
    collections({
      recos: [
        {
          data: {
            id: 'ubm-0001',
            sourceId: { id: 'un-bon-moment' },
            episodeGuid: 'guid-42',
            title: 'Sans métadonnées',
            recommendedBy: '',
            timestamp: '',
          },
        },
      ],
      episodes: [],
    });
    const res = await submit();
    expect(res.status).toBe(200);

    const [, opts] = notifyReportMatrix.mock.calls[0] as [unknown, { context: Record<string, unknown> }];
    expect(opts.context).toEqual({
      recoTitle: 'Sans métadonnées',
      // `types` absent → chaîne vide → `undefined`.
      recoTypes: undefined,
      recommendedBy: undefined,
      timestamp: undefined,
      // Aucun épisode ne matche le guid.
      episodeLabel: undefined,
      episodeTitle: undefined,
      url: `${SELF}/un-bon-moment/episode/guid-42`,
    });
  });

  it('renvoie un contexte vide quand la reco est introuvable', async () => {
    collections({
      recos: [
        {
          data: {
            id: 'un-autre-id',
            sourceId: { id: 'un-bon-moment' },
            episodeGuid: 'guid-1',
            title: 'Autre',
          },
        },
      ],
      episodes: [],
    });
    const res = await submit();
    expect(res.status).toBe(200);

    const [, opts] = notifyReportMatrix.mock.calls[0] as [unknown, { context: Record<string, unknown> }];
    expect(opts.context).toEqual({});
    // La collection `episodes` n'est même pas chargée si la reco est absente.
    expect(getCollection.mock.calls.map((c) => c[0])).toEqual(['recos']);
  });

  it('renvoie un contexte vide si getCollection échoue (best-effort)', async () => {
    getCollection.mockRejectedValue(new Error('content layer indisponible'));
    const res = await submit();

    // L'échec de résolution ne doit PAS faire échouer le signalement.
    expect(res.status).toBe(200);
    const [, opts] = notifyReportMatrix.mock.calls[0] as [unknown, { context: Record<string, unknown> }];
    expect(opts.context).toEqual({});
  });

  it('ne notifie pas quand le signalement est rejeté', async () => {
    seedFull();
    const route = await loadRoute();
    const fields = { ...validFields(route.makeChallenge()), captchaAnswer: '0' };
    const res = (await route.POST(ctxFor(formRequest(fields)))) as Response;

    expect(res.status).toBe(400);
    expect(notifyReportMatrix).not.toHaveBeenCalled();
  });
});
