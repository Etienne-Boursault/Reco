/**
 * tests/og/test_og_endpoint_cov.test.ts
 *
 * Endpoint OG PNG (`src/pages/og/[...slug].png.ts`).
 *
 * `getStaticPaths` est la vraie logique : quelles cartes sont générées au
 * build, et avec quelles props. On la teste exhaustivement en mockant
 * `astro:content`. `renderOG` (Satori + resvg, ~1 s par rendu) est mocké :
 * son intégration est déjà couverte par `test_og_render.test.ts`, ici seule
 * compte la glue endpoint → renderer.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const getCollection = vi.fn();
const renderOG = vi.fn(async () => new Uint8Array([0x89, 0x50, 0x4e, 0x47]));

vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

vi.mock('../../src/lib/og/renderer.js', () => ({
  renderOG: (...args: unknown[]) => renderOG(...(args as [])),
}));

interface Entry {
  id?: string;
  data: Record<string, unknown>;
}

function collections(map: Record<string, Entry[]>): void {
  getCollection.mockImplementation(async (name: string) => map[name] ?? []);
}

type Route = typeof import('../../src/pages/og/[...slug].png.js');

async function loadRoute(): Promise<Route> {
  return (await import('../../src/pages/og/[...slug].png.js')) as unknown as Route;
}

interface Path {
  params: { slug: string };
  props: Record<string, unknown>;
}

async function paths(): Promise<Path[]> {
  const { getStaticPaths } = await loadRoute();
  return (await getStaticPaths({} as never)) as unknown as Path[];
}

beforeEach(() => {
  getCollection.mockReset();
  renderOG.mockClear();
});

describe('getStaticPaths — carte par défaut', () => {
  it('génère /og/default.png même sans aucun contenu', async () => {
    collections({ sources: [], episodes: [], recos: [] });
    const all = await paths();

    expect(all).toHaveLength(1);
    expect(all[0].params.slug).toBe('default');
    expect(all[0].props).toEqual({
      title: 'Reco',
      subtitle: 'Catalogue de recommandations de podcasts',
      emoji: '🎙️',
      typeLabel: 'Catalogue',
      sourceLabel: 'source-internet.fr',
    });
  });

  it('charge les trois collections nécessaires', async () => {
    collections({ sources: [], episodes: [], recos: [] });
    await paths();

    expect(getCollection.mock.calls.map((c) => c[0]).sort()).toEqual([
      'episodes',
      'recos',
      'sources',
    ]);
  });
});

describe('getStaticPaths — cartes de source', () => {
  it('reprend tagline, thème et titre de la source', async () => {
    collections({
      sources: [
        {
          id: 'ubm',
          data: {
            title: 'Un Bon Moment',
            tagline: 'Le podcast',
            theme: { colors: { accent: '#ff0066', bg: '#101010' } },
          },
        },
      ],
      episodes: [],
      recos: [],
    });
    const card = (await paths()).find((p) => p.params.slug === 'ubm');

    expect(card?.props).toEqual({
      title: 'Un Bon Moment',
      subtitle: 'Le podcast',
      emoji: '🎙️',
      typeLabel: 'Podcast',
      sourceLabel: 'Un Bon Moment',
      accent: '#ff0066',
      bg: '#101010',
    });
  });

  it('retombe sur les 80 premiers caractères de description sans tagline', async () => {
    const description = 'D'.repeat(200);
    collections({
      sources: [{ id: 'ubm', data: { title: 'Un Bon Moment', description } }],
      episodes: [],
      recos: [],
    });
    const card = (await paths()).find((p) => p.params.slug === 'ubm');

    expect(card?.props.subtitle).toBe('D'.repeat(80));
  });

  it('laisse subtitle et thème indéfinis quand tout manque', async () => {
    collections({
      sources: [{ id: 'ubm', data: { title: 'Nu' } }],
      episodes: [],
      recos: [],
    });
    const card = (await paths()).find((p) => p.params.slug === 'ubm');

    expect(card?.props.subtitle).toBeUndefined();
    expect(card?.props.accent).toBeUndefined();
    expect(card?.props.bg).toBeUndefined();
  });
});

describe('getStaticPaths — cartes d’épisode', () => {
  const source: Entry = {
    id: 'ubm',
    data: {
      title: 'Un Bon Moment',
      theme: { colors: { accent: '#abc123', bg: '#000000' } },
    },
  };

  function reco(guid: string, status = 'validated'): Entry {
    return { data: { status, sourceId: { id: 'ubm' }, episodeGuid: guid } };
  }

  it('génère une carte pour un épisode ayant une reco non écartée', async () => {
    collections({
      sources: [source],
      episodes: [
        { data: { guid: 'guid-1', sourceId: { id: 'ubm' }, title: 'Titre RSS' } },
      ],
      recos: [reco('guid-1')],
    });
    const card = (await paths()).find((p) => p.params.slug.includes('episode'));

    expect(card?.params.slug).toBe('ubm/episode/guid-1');
    expect(card?.props).toEqual({
      title: 'Titre RSS',
      subtitle: 'Un Bon Moment',
      emoji: '🎙️',
      typeLabel: 'Épisode',
      sourceLabel: 'Un Bon Moment',
      accent: '#abc123',
      bg: '#000000',
    });
  });

  it('préfère le titre YouTube au titre RSS', async () => {
    collections({
      sources: [source],
      episodes: [
        {
          data: {
            guid: 'guid-1',
            sourceId: { id: 'ubm' },
            title: 'Titre RSS',
            youtubeTitle: 'Titre YouTube',
          },
        },
      ],
      recos: [reco('guid-1')],
    });
    const card = (await paths()).find((p) => p.params.slug.includes('episode'));

    expect(card?.props.title).toBe('Titre YouTube');
  });

  it('ignore les épisodes sans reco valide', async () => {
    collections({
      sources: [source],
      episodes: [{ data: { guid: 'orphelin', sourceId: { id: 'ubm' }, title: 'X' } }],
      recos: [],
    });
    const all = await paths();

    expect(all.some((p) => p.params.slug.includes('episode'))).toBe(false);
  });

  it('ignore les épisodes dont toutes les recos sont discarded', async () => {
    collections({
      sources: [source],
      episodes: [{ data: { guid: 'guid-1', sourceId: { id: 'ubm' }, title: 'X' } }],
      recos: [reco('guid-1', 'discarded')],
    });
    const all = await paths();

    expect(all.some((p) => p.params.slug.includes('episode'))).toBe(false);
  });

  it("ignore les épisodes dont la source n'existe pas (P2-P garde-fou)", async () => {
    collections({
      sources: [source],
      episodes: [{ data: { guid: 'guid-2', sourceId: { id: 'inconnue' }, title: 'X' } }],
      recos: [{ data: { status: 'validated', sourceId: { id: 'inconnue' }, episodeGuid: 'guid-2' } }],
    });
    const all = await paths();

    expect(all.some((p) => p.params.slug.includes('episode'))).toBe(false);
  });

  it('ignore les épisodes avec une miniature YouTube (économie ~80 KB/carte)', async () => {
    collections({
      sources: [source],
      episodes: [
        {
          data: {
            guid: 'guid-1',
            sourceId: { id: 'ubm' },
            title: 'X',
            youtubeUrl: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
          },
        },
      ],
      recos: [reco('guid-1')],
    });
    const all = await paths();

    expect(all.some((p) => p.params.slug.includes('episode'))).toBe(false);
  });

  it('génère la carte si youtubeUrl ne contient pas de paramètre v=', async () => {
    collections({
      sources: [source],
      episodes: [
        {
          data: {
            guid: 'guid-1',
            sourceId: { id: 'ubm' },
            title: 'X',
            youtubeUrl: 'https://youtu.be/dQw4w9WgXcQ',
          },
        },
      ],
      recos: [reco('guid-1')],
    });
    const all = await paths();

    expect(all.some((p) => p.params.slug === 'ubm/episode/guid-1')).toBe(true);
  });

  it('ne mélange pas les sources sur un guid identique', async () => {
    collections({
      sources: [source, { id: 'autre', data: { title: 'Autre' } }],
      episodes: [
        { data: { guid: 'guid-1', sourceId: { id: 'autre' }, title: 'Chez Autre' } },
      ],
      // La reco appartient à `ubm`, pas à `autre` → clé `src::guid` distincte.
      recos: [reco('guid-1')],
    });
    const all = await paths();

    expect(all.some((p) => p.params.slug.includes('episode'))).toBe(false);
  });
});

describe('getStaticPaths — slugs URL-safe', () => {
  it('assainit les guid exotiques (majuscules, espaces, ponctuation)', async () => {
    collections({
      sources: [{ id: 'UBM Podcast', data: { title: 'Un Bon Moment' } }],
      episodes: [
        {
          data: {
            guid: 'Épisode #42 / Spécial !!',
            sourceId: { id: 'UBM Podcast' },
            title: 'X',
          },
        },
      ],
      recos: [
        {
          data: {
            status: 'validated',
            sourceId: { id: 'UBM Podcast' },
            episodeGuid: 'Épisode #42 / Spécial !!',
          },
        },
      ],
    });
    const card = (await paths()).find((p) => p.params.slug.includes('/episode/'));

    // Minuscules, caractères hors [a-z0-9_-] remplacés, tirets compressés.
    expect(card?.params.slug).toBe('ubm-podcast/episode/-pisode-42-sp-cial-');
    expect(card?.params.slug).toMatch(/^[a-z0-9_/-]+$/);
  });
});

describe('GET — rendu de la carte', () => {
  it('délègue les props à renderOG et renvoie un PNG', async () => {
    const { GET } = await loadRoute();
    const props = { title: 'Dune', subtitle: 'Un Bon Moment', emoji: '🎬' };
    const res = (await GET({ props } as never)) as Response;

    expect(renderOG).toHaveBeenCalledWith(props);
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('image/png');
    // H4 : pas de Cache-Control ici — c'est le serveur statique qui décide.
    expect(res.headers.get('Cache-Control')).toBeNull();

    const bytes = new Uint8Array(await res.arrayBuffer());
    expect(Array.from(bytes.slice(0, 4))).toEqual([0x89, 0x50, 0x4e, 0x47]);
  });
});
