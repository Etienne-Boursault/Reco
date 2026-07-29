/**
 * tests/registry/test_registry_endpoint_cov.test.ts
 *
 * Endpoint `/.well-known/reco-registry.json`
 * (`src/pages/.well-known/reco-registry.json.ts`).
 *
 * L'endpoint orchestre : chargement des collections → sélection de la source
 * → `buildRegistry` → validation `parseRegistry` → sérialisation. On mocke
 * `astro:content` à la frontière (aucun accès disque aux collections) et on
 * couvre :
 *   - le cache (`RECO_REGISTRY_CACHE_MAX_AGE`, valide / invalide / absent) ;
 *   - le fallback `siteUrl` quand `Astro.site` n'est pas configuré (M24-9) ;
 *   - le fallback « aucune source » (M24-8) ;
 *   - la sélection alphabétique + le bloc `podcasts` multi-source (F-H-3),
 *     avec normalisation de `language` ;
 *   - `manifestoUrl` opt-in selon l'existence de la page (F-H-4) ;
 *   - `deterministicNowIso` (F-CRIT-4) ;
 *   - le 500 `registry_validation_failed` (F-CRIT-5).
 *
 * NB : `existsSync` n'est PAS mocké — on pilote `RECO_MANIFESTO_PATH` vers
 * une page réelle (`/manifeste`) ou inexistante, ce qui teste le vrai
 * comportement plutôt qu'un double.
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

type Route = typeof import('../../src/pages/.well-known/reco-registry.json.js');

/**
 * Ré-importe la route après `resetModules` : indispensable car
 * `CACHE_MAX_AGE` et `GENERATOR` sont calculés au chargement du module.
 */
async function loadRoute(): Promise<Route> {
  vi.resetModules();
  return (await import(
    '../../src/pages/.well-known/reco-registry.json.js'
  )) as unknown as Route;
}

function ctx(site?: string): Parameters<Route['GET']>[0] {
  return { site: site ? new URL(site) : undefined } as never;
}

/** Source + contenus nominaux (1 source, 1 épisode, 1 œuvre, 1 mention). */
function seedNominal(over: Partial<Record<string, Entry[]>> = {}): void {
  collections({
    sources: [
      {
        id: 'ubm',
        data: {
          id: 'ubm',
          title: 'Un Bon Moment',
          tagline: 'Le podcast',
          hosts: ['Adèle'],
          rssUrl: 'https://feeds.example/ubm.xml',
          lang: 'fr',
        },
      },
    ],
    episodes: [{ data: { sourceId: { id: 'ubm' }, date: '2026-03-14' } }],
    items: [{ data: { id: 'w-1', title: 'Dune', types: ['film'] } }],
    mentions: [
      {
        data: {
          itemId: 'w-1',
          recommendedBy: 'Bruno',
          status: 'validated',
          sourceRef: { sourceId: 'ubm' },
        },
      },
    ],
    ...over,
  });
}

const ENV_KEYS = [
  'RECO_REGISTRY_CACHE_MAX_AGE',
  'RECO_BUILD_TIMESTAMP',
  'SOURCE_DATE_EPOCH',
  'RECO_MANIFESTO_PATH',
] as const;
const SAVED: Record<string, string | undefined> = {};

beforeEach(() => {
  getCollection.mockReset();
  for (const k of ENV_KEYS) {
    SAVED[k] = process.env[k];
    delete process.env[k];
  }
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (SAVED[k] === undefined) delete process.env[k];
    else process.env[k] = SAVED[k] as string;
  }
});

describe('reco-registry.json — enveloppe HTTP', () => {
  it('est marqué prerender (F-CRIT-3)', async () => {
    const mod = await loadRoute();
    expect(mod.prerender).toBe(true);
  });

  it('émet application/json UTF-8 + Cache-Control 1 h par défaut', async () => {
    seedNominal();
    const { GET } = await loadRoute();
    const res = (await GET(ctx('https://reco.example/'))) as Response;

    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('application/json; charset=utf-8');
    expect(res.headers.get('Cache-Control')).toBe('public, max-age=3600, must-revalidate');
  });

  it('honore RECO_REGISTRY_CACHE_MAX_AGE quand la valeur est valide', async () => {
    process.env.RECO_REGISTRY_CACHE_MAX_AGE = '120';
    seedNominal();
    const { GET } = await loadRoute();
    const res = (await GET(ctx('https://reco.example/'))) as Response;

    expect(res.headers.get('Cache-Control')).toBe('public, max-age=120, must-revalidate');
  });

  it('ignore une valeur de cache non numérique (retour à 3600)', async () => {
    process.env.RECO_REGISTRY_CACHE_MAX_AGE = 'beaucoup';
    seedNominal();
    const { GET } = await loadRoute();
    const res = (await GET(ctx('https://reco.example/'))) as Response;

    expect(res.headers.get('Cache-Control')).toBe('public, max-age=3600, must-revalidate');
  });

  it('ignore une valeur de cache négative ou nulle (retour à 3600)', async () => {
    process.env.RECO_REGISTRY_CACHE_MAX_AGE = '0';
    seedNominal();
    const { GET } = await loadRoute();
    const res = (await GET(ctx('https://reco.example/'))) as Response;

    expect(res.headers.get('Cache-Control')).toBe('public, max-age=3600, must-revalidate');
  });

  it('sérialise sans pretty-print (F-M-2)', async () => {
    seedNominal();
    const { GET } = await loadRoute();
    const text = await ((await GET(ctx('https://reco.example/'))) as Response).text();

    expect(text).not.toMatch(/\n\s\s/);
  });
});

describe('reco-registry.json — document nominal', () => {
  it('expose la source, ses stats et les endpoints du kit', async () => {
    seedNominal();
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      schemaVersion: number;
      siteUrl: string;
      podcast: { title: string; hosts: string[]; language: string; rssUrl?: string };
      stats: { itemsCount: number; mentionsCount: number; episodesCount: number };
      meta: { generator: string; manifesto?: string };
      endpoints: { search: string };
      podcasts?: unknown;
    };

    expect(body.schemaVersion).toBe(1);
    // Le trailing slash de `Astro.site` est retiré.
    expect(body.siteUrl).toBe('https://reco.example');
    expect(body.podcast.title).toBe('Un Bon Moment');
    expect(body.podcast.hosts).toEqual(['Adèle']);
    expect(body.podcast.rssUrl).toBe('https://feeds.example/ubm.xml');
    expect(body.stats.episodesCount).toBe(1);
    expect(body.stats.mentionsCount).toBe(1);
    expect(body.stats.itemsCount).toBe(1);
    expect(body.meta.generator).toMatch(/^Reco\/\d/);
    expect(body.endpoints.search).toBe('/search.json');
    // Mono-source : pas de bloc `podcasts`.
    expect(body.podcasts).toBeUndefined();
  });

  it('dérive lastUpdatedAt de max(episode.date) (H24-3)', async () => {
    seedNominal({
      episodes: [
        { data: { sourceId: { id: 'ubm' }, date: '2025-01-01' } },
        { data: { sourceId: { id: 'ubm' }, date: '2026-05-20' } },
      ],
    });
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      stats: { lastUpdatedAt: string };
    };

    expect(body.stats.lastUpdatedAt.slice(0, 10)).toBe('2026-05-20');
  });

  it('tolère lang / hosts / date / recommendedBy / types absents', async () => {
    collections({
      sources: [{ id: 'ubm', data: { id: 'ubm', title: 'Minimal' } }],
      episodes: [{ data: { sourceId: { id: 'ubm' } } }],
      items: [{ data: { id: 'w-1', title: 'Sans type' } }],
      mentions: [
        { data: { itemId: 'w-1', status: 'validated', sourceRef: { sourceId: 'ubm' } } },
      ],
    });
    const { GET } = await loadRoute();
    const res = (await GET(ctx('https://reco.example/'))) as Response;
    const body = (await res.json()) as {
      podcast: { language: string; hosts: string[] };
      stats: { guestsCount: number };
    };

    expect(res.status).toBe(200);
    expect(body.podcast.language).toBe('fr');
    expect(body.podcast.hosts).toEqual([]);
    expect(body.stats.guestsCount).toBe(0);
  });

  it("filtre épisodes et mentions sur l'id de la source retenue (R-P1-01)", async () => {
    collections({
      sources: [
        { id: 'aaa', data: { id: 'aaa', title: 'Premier', lang: 'fr' } },
        { id: 'bbb', data: { id: 'bbb', title: 'Second', lang: 'fr' } },
      ],
      episodes: [
        { data: { sourceId: { id: 'aaa' }, date: '2026-01-01' } },
        { data: { sourceId: { id: 'bbb' }, date: '2026-02-01' } },
        { data: { sourceId: { id: 'bbb' }, date: '2026-03-01' } },
      ],
      items: [{ data: { id: 'w-1', title: 'Dune', types: ['film'] } }],
      mentions: [
        {
          data: {
            itemId: 'w-1',
            recommendedBy: 'X',
            status: 'validated',
            sourceRef: { sourceId: 'bbb' },
          },
        },
      ],
    });
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      podcast: { title: string };
      stats: { episodesCount: number; mentionsCount: number };
    };

    // Sélection alphabétique : `aaa` gagne.
    expect(body.podcast.title).toBe('Premier');
    expect(body.stats.episodesCount).toBe(1);
    // La mention appartient à `bbb` → non comptée.
    expect(body.stats.mentionsCount).toBe(0);
  });
});

describe('reco-registry.json — siteUrl', () => {
  it('retombe sur https://example.invalid sans Astro.site (M24-9)', async () => {
    seedNominal();
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx())) as Response).json()) as { siteUrl: string };

    expect(body.siteUrl).toBe('https://example.invalid');
  });
});

describe('reco-registry.json — fallback sans source (M24-8)', () => {
  it('renvoie un document valide « unknown » plutôt qu’une erreur', async () => {
    collections({ sources: [], episodes: [], items: [], mentions: [] });
    const { GET } = await loadRoute();
    const res = (await GET(ctx('https://reco.example/'))) as Response;
    const body = (await res.json()) as {
      schemaVersion: number;
      podcast: { title: string; hosts: string[]; language: string };
      stats: { episodesCount: number; itemsCount: number };
    };

    expect(res.status).toBe(200);
    expect(body.schemaVersion).toBe(1);
    expect(body.podcast.title).toBe('Reco');
    expect(body.podcast.hosts).toEqual([]);
    expect(body.podcast.language).toBe('fr');
    expect(body.stats.episodesCount).toBe(0);
    expect(body.stats.itemsCount).toBe(0);
  });

  it('le fallback conserve le Cache-Control standard', async () => {
    collections({ sources: [], episodes: [], items: [], mentions: [] });
    const { GET } = await loadRoute();
    const res = (await GET(ctx('https://reco.example/'))) as Response;

    expect(res.headers.get('Cache-Control')).toBe('public, max-age=3600, must-revalidate');
  });
});

describe('reco-registry.json — multi-source (F-H-3)', () => {
  function seedMulti(langs: Array<string | undefined>): void {
    collections({
      sources: langs.map((lang, i) => ({
        id: `s${i}`,
        data: {
          id: `s${i}`,
          title: `Podcast ${i}`,
          tagline: `Tagline ${i}`,
          rssUrl: `https://feeds.example/s${i}.xml`,
          hosts: [`Hôte ${i}`],
          ...(lang === undefined ? {} : { lang }),
        },
      })),
      episodes: [],
      items: [],
      mentions: [],
    });
  }

  it('peuple `podcasts` avec toutes les sources triées', async () => {
    seedMulti(['fr', 'en']);
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      podcast: { title: string };
      podcasts: Array<{ title: string; language: string; hosts: string[]; rssUrl?: string }>;
    };

    expect(body.podcast.title).toBe('Podcast 0');
    expect(body.podcasts.map((p) => p.title)).toEqual(['Podcast 0', 'Podcast 1']);
    expect(body.podcasts[1].language).toBe('en');
    expect(body.podcasts[0].hosts).toEqual(['Hôte 0']);
    expect(body.podcasts[0].rssUrl).toBe('https://feeds.example/s0.xml');
  });

  it('normalise les langues BCP-47 (`fr-FR` → `fr`) et majuscules', async () => {
    seedMulti(['fr-FR', 'EN_US']);
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      podcasts: Array<{ language: string }>;
    };

    expect(body.podcasts.map((p) => p.language)).toEqual(['fr', 'en']);
  });

  it('retombe sur `fr` pour une langue absente ou non alphabétique', async () => {
    seedMulti([undefined, '42']);
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      podcasts: Array<{ language: string }>;
    };

    expect(body.podcasts.map((p) => p.language)).toEqual(['fr', 'fr']);
  });

  it('tolère une source multi sans `hosts`', async () => {
    collections({
      sources: [
        { id: 'a', data: { id: 'a', title: 'A', lang: 'fr' } },
        { id: 'b', data: { id: 'b', title: 'B', lang: 'fr' } },
      ],
      episodes: [],
      items: [],
      mentions: [],
    });
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      podcasts: Array<{ hosts: string[] }>;
    };

    expect(body.podcasts.map((p) => p.hosts)).toEqual([[], []]);
  });
});

describe('reco-registry.json — manifestoUrl (F-H-4)', () => {
  it('expose le lien quand la page existe (défaut /manifeste)', async () => {
    seedNominal();
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      meta: { manifesto?: string };
    };

    expect(body.meta.manifesto).toBe('https://reco.example/manifeste');
  });

  it("n'expose rien quand la page ciblée n'existe pas", async () => {
    process.env.RECO_MANIFESTO_PATH = '/page-qui-nexiste-pas-du-tout';
    seedNominal();
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      meta: { manifesto?: string };
    };

    expect(body.meta.manifesto).toBeUndefined();
  });

  it('accepte un chemin sans slash initial', async () => {
    process.env.RECO_MANIFESTO_PATH = '/manifeste';
    seedNominal();
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      meta: { manifesto?: string };
    };

    expect(body.meta.manifesto).toBe('https://reco.example/manifeste');
  });
});

describe('reco-registry.json — generatedAt déterministe (F-CRIT-4)', () => {
  async function generatedAt(): Promise<string> {
    seedNominal();
    const { GET } = await loadRoute();
    const body = (await ((await GET(ctx('https://reco.example/'))) as Response).json()) as {
      meta: { generatedAt: string };
    };
    return body.meta.generatedAt;
  }

  it('RECO_BUILD_TIMESTAMP en secondes', async () => {
    process.env.RECO_BUILD_TIMESTAMP = '1700000000';
    expect(await generatedAt()).toBe(new Date(1700000000 * 1000).toISOString());
  });

  it('RECO_BUILD_TIMESTAMP en millisecondes (> 1e12)', async () => {
    process.env.RECO_BUILD_TIMESTAMP = '1700000000000';
    expect(await generatedAt()).toBe(new Date(1700000000000).toISOString());
  });

  it('SOURCE_DATE_EPOCH en repli', async () => {
    process.env.SOURCE_DATE_EPOCH = '1600000000';
    expect(await generatedAt()).toBe(new Date(1600000000 * 1000).toISOString());
  });

  it('valeur invalide → `now`', async () => {
    process.env.SOURCE_DATE_EPOCH = 'nope';
    const before = Date.now();
    const t = new Date(await generatedAt()).getTime();
    const after = Date.now();

    expect(t).toBeGreaterThanOrEqual(before - 1000);
    expect(t).toBeLessThanOrEqual(after + 1000);
  });

  it('aucune variable → `now`', async () => {
    const before = Date.now();
    const t = new Date(await generatedAt()).getTime();

    expect(t).toBeGreaterThanOrEqual(before - 1000);
  });
});

describe('reco-registry.json — validation du schema (F-CRIT-5)', () => {
  it('renvoie 500 registry_validation_failed si le document dérive', async () => {
    // `title` dépasse `REGISTRY_LIMITS.titleMax` (200) → ZodError.
    seedNominal({
      sources: [
        { id: 'ubm', data: { id: 'ubm', title: 'x'.repeat(500), hosts: [], lang: 'fr' } },
      ],
    });
    const { GET } = await loadRoute();
    const res = (await GET(ctx('https://reco.example/'))) as Response;
    const body = (await res.json()) as { error: string; message: string };

    expect(res.status).toBe(500);
    expect(body.error).toBe('registry_validation_failed');
    expect(body.message).toMatch(/200|too_big|at most/i);
    // Même en erreur, l'endpoint reste du JSON avec le header de cache.
    expect(res.headers.get('Content-Type')).toBe('application/json; charset=utf-8');
  });

  it('sérialise une exception non-Error via String(err)', async () => {
    vi.resetModules();
    // On force `parseRegistry` à lever une valeur non-Error pour couvrir la
    // branche `String(err)` du catch (impossible avec une vraie ZodError).
    vi.doMock('../../src/lib/registry/types', async (importOriginal) => {
      const actual = (await importOriginal()) as Record<string, unknown>;
      return {
        ...actual,
        parseRegistry: () => {
          throw 'boom-non-error';
        },
      };
    });
    seedNominal();
    const mod = (await import(
      '../../src/pages/.well-known/reco-registry.json.js'
    )) as unknown as Route;
    const res = (await mod.GET(ctx('https://reco.example/'))) as Response;
    const body = (await res.json()) as { error: string; message: string };

    expect(res.status).toBe(500);
    expect(body.error).toBe('registry_validation_failed');
    expect(body.message).toBe('boom-non-error');

    vi.doUnmock('../../src/lib/registry/types');
    vi.resetModules();
  });
});
