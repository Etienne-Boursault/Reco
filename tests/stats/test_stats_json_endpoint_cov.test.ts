/**
 * tests/stats/test_stats_json_endpoint_cov.test.ts
 *
 * Endpoint `/stats.json` (`src/pages/stats.json.ts`).
 *
 * Couvre :
 *  - headers (Content-Type + Cache-Control 1 h, F-M-1) ;
 *  - projection des 4 collections vers `buildStatsSnapshot` ;
 *  - `deterministicNowIso` (F-CRIT-4) : `RECO_BUILD_TIMESTAMP`,
 *    `SOURCE_DATE_EPOCH`, secondes vs millisecondes, valeurs invalides,
 *    absence totale d'env → `now`.
 *
 * `astro:content` est mocké à la frontière : aucun accès disque.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const getCollection = vi.fn();

vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

interface Entry {
  id?: string;
  data: Record<string, unknown>;
}

function collections(map: Record<string, Entry[]>): void {
  getCollection.mockImplementation(async (name: string) => map[name] ?? []);
}

function ctx(): never {
  return {} as never;
}

async function loadRoute() {
  return await import('../../src/pages/stats.json.js');
}

/** Jeu de données minimal mais réaliste (1 source, 1 épisode, 1 œuvre). */
function seedNominal(): void {
  collections({
    sources: [{ id: 'ubm', data: { id: 'ubm', hosts: ['Adèle'] } }],
    episodes: [{ data: { sourceId: { id: 'ubm' }, date: '2026-03-14' } }],
    mentions: [
      {
        data: {
          itemId: 'w-1',
          recommendedBy: 'Adèle',
          status: 'validated',
          sourceRef: { sourceId: 'ubm' },
        },
      },
    ],
    items: [{ data: { id: 'w-1', title: 'Dune', types: ['film'] } }],
  });
}

const SAVED = {
  RECO_BUILD_TIMESTAMP: process.env.RECO_BUILD_TIMESTAMP,
  SOURCE_DATE_EPOCH: process.env.SOURCE_DATE_EPOCH,
};

beforeEach(() => {
  getCollection.mockReset();
  delete process.env.RECO_BUILD_TIMESTAMP;
  delete process.env.SOURCE_DATE_EPOCH;
});

afterEach(() => {
  for (const [k, v] of Object.entries(SAVED)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
});

describe('GET /stats.json — enveloppe HTTP', () => {
  it('émet application/json UTF-8 avec un cache 1 h', async () => {
    collections({ sources: [], episodes: [], mentions: [], items: [] });
    const { GET } = await loadRoute();
    const res = await GET(ctx());

    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('application/json; charset=utf-8');
    expect(res.headers.get('Cache-Control')).toBe('public, max-age=3600, must-revalidate');
  });

  it('est marqué prerender (endpoint statique, F-CRIT-3)', async () => {
    const mod = await loadRoute();
    expect(mod.prerender).toBe(true);
  });

  it('charge les quatre collections attendues', async () => {
    collections({ sources: [], episodes: [], mentions: [], items: [] });
    const { GET } = await loadRoute();
    await GET(ctx());

    expect(getCollection.mock.calls.map((c) => c[0]).sort()).toEqual([
      'episodes',
      'items',
      'mentions',
      'sources',
    ]);
  });

  it('sérialise sans pretty-print (F-M-2)', async () => {
    seedNominal();
    const { GET } = await loadRoute();
    const text = await (await GET(ctx())).text();

    expect(text).not.toMatch(/\n\s\s/);
  });
});

describe('GET /stats.json — projection des collections', () => {
  it('agrège les compteurs globaux à partir des collections', async () => {
    seedNominal();
    const { GET } = await loadRoute();
    const body = (await (await GET(ctx())).json()) as {
      schemaVersion: number;
      global: {
        podcastsCount: number;
        episodesCount: number;
        recommendationsCount: number;
        uniqueWorksCount: number;
      };
      perSource: Record<string, { episodesCount: number }>;
      monthlyEpisodes: Array<{ month: string; count: number }>;
    };

    expect(body.schemaVersion).toBe(1);
    expect(body.global.podcastsCount).toBe(1);
    expect(body.global.episodesCount).toBe(1);
    expect(body.global.recommendationsCount).toBe(1);
    expect(body.global.uniqueWorksCount).toBe(1);
    // La projection `sourceId.id` alimente bien le découpage par source.
    expect(body.perSource.ubm.episodesCount).toBe(1);
    // La projection `date` alimente le chart mensuel.
    expect(body.monthlyEpisodes).toEqual([{ month: '2026-03', count: 1 }]);
  });

  it('tolère hosts / date / recommendedBy absents (fallbacks ?? )', async () => {
    collections({
      sources: [{ id: 'ubm', data: { id: 'ubm' } }],
      episodes: [{ data: { sourceId: { id: 'ubm' } } }],
      mentions: [
        {
          data: {
            itemId: 'w-1',
            status: 'validated',
            sourceRef: { sourceId: 'ubm' },
          },
        },
      ],
      items: [{ data: { id: 'w-1', title: 'Sans hôte', types: ['livre'] } }],
    });
    const { GET } = await loadRoute();
    const res = await GET(ctx());
    const body = (await res.json()) as {
      global: { uniqueGuestsCount: number; episodesCount: number };
      monthlyEpisodes: unknown[];
    };

    expect(res.status).toBe(200);
    // `recommendedBy` absent → aucun invité comptabilisé.
    expect(body.global.uniqueGuestsCount).toBe(0);
    expect(body.global.episodesCount).toBe(1);
    // `date` absente → pas de bucket mensuel.
    expect(body.monthlyEpisodes).toHaveLength(0);
  });

  it("exclut les hosts du décompte d'invités (source.hosts transmis)", async () => {
    collections({
      sources: [{ id: 'ubm', data: { id: 'ubm', hosts: ['Adèle'] } }],
      episodes: [],
      mentions: [
        {
          data: {
            itemId: 'w-1',
            recommendedBy: 'Adèle',
            status: 'validated',
            sourceRef: { sourceId: 'ubm' },
          },
        },
        {
          data: {
            itemId: 'w-1',
            recommendedBy: 'Bruno',
            status: 'validated',
            sourceRef: { sourceId: 'ubm' },
          },
        },
      ],
      items: [{ data: { id: 'w-1', title: 'Dune', types: ['film'] } }],
    });
    const { GET } = await loadRoute();
    const body = (await (await GET(ctx())).json()) as {
      global: { uniqueGuestsCount: number };
      topGuests: Array<{ name: string }>;
    };

    // Adèle est hôte (transmise via `hosts`), seul Bruno compte comme invité.
    expect(body.global.uniqueGuestsCount).toBe(1);
    expect(body.topGuests.map((g) => g.name)).toEqual(['Bruno']);
  });
});

describe('deterministicNowIso (F-CRIT-4) via /stats.json', () => {
  async function generatedAt(): Promise<string> {
    collections({ sources: [], episodes: [], mentions: [], items: [] });
    const { GET } = await loadRoute();
    const body = (await (await GET(ctx())).json()) as { generatedAt: string };
    return body.generatedAt;
  }

  it('RECO_BUILD_TIMESTAMP en secondes → ISO déterministe', async () => {
    process.env.RECO_BUILD_TIMESTAMP = '1700000000';
    expect(await generatedAt()).toBe(new Date(1700000000 * 1000).toISOString());
  });

  it('RECO_BUILD_TIMESTAMP en millisecondes (> 1e12) → pas de ×1000', async () => {
    process.env.RECO_BUILD_TIMESTAMP = '1700000000000';
    expect(await generatedAt()).toBe(new Date(1700000000000).toISOString());
  });

  it('SOURCE_DATE_EPOCH sert de repli quand RECO_BUILD_TIMESTAMP est absent', async () => {
    process.env.SOURCE_DATE_EPOCH = '1600000000';
    expect(await generatedAt()).toBe(new Date(1600000000 * 1000).toISOString());
  });

  it('RECO_BUILD_TIMESTAMP a priorité sur SOURCE_DATE_EPOCH', async () => {
    process.env.RECO_BUILD_TIMESTAMP = '1700000000';
    process.env.SOURCE_DATE_EPOCH = '1600000000';
    expect(await generatedAt()).toBe(new Date(1700000000 * 1000).toISOString());
  });

  it('valeur non numérique → retombe sur `now`', async () => {
    process.env.RECO_BUILD_TIMESTAMP = 'pas-un-nombre';
    const before = Date.now();
    const iso = await generatedAt();
    const after = Date.now();
    const t = new Date(iso).getTime();

    expect(Number.isNaN(t)).toBe(false);
    expect(t).toBeGreaterThanOrEqual(before - 1000);
    expect(t).toBeLessThanOrEqual(after + 1000);
  });

  it('valeur négative ou nulle → retombe sur `now`', async () => {
    process.env.RECO_BUILD_TIMESTAMP = '0';
    const before = Date.now();
    const t = new Date(await generatedAt()).getTime();

    expect(t).toBeGreaterThanOrEqual(before - 1000);
  });

  it('aucune variable → `now`', async () => {
    const before = Date.now();
    const t = new Date(await generatedAt()).getTime();
    const after = Date.now();

    expect(t).toBeGreaterThanOrEqual(before - 1000);
    expect(t).toBeLessThanOrEqual(after + 1000);
  });
});
