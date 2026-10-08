/**
 * tests/og/test_og_endpoint_cov.test.ts
 *
 * Endpoint OG PNG (`src/pages/og/[...slug].png.ts`).
 *
 * `getStaticPaths` lit les collections et les met à plat pour
 * `lib/og/cartes.ts`, qui décide des cartes (testé dans `test_cartes`). Ici,
 * seulement la lecture, les slugs et la glue, en mockant `astro:content`. `renderOG` (Satori + resvg, ~1 s par rendu) est mocké :
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

describe('getStaticPaths — lecture des collections', () => {
  it('génère /og/default.png même sans aucun contenu', async () => {
    collections({});
    const all = await paths();

    expect(all.map((p) => p.params.slug)).toEqual(['default']);
    expect(all[0].props).toMatchObject({ gabarit: 'etiquette', chiffre: 0, rubrique: 'Catalogue' });
  });

  it('charge les cinq collections dont les cartes tirent leurs chiffres', async () => {
    collections({});
    await paths();

    expect(getCollection.mock.calls.map((c) => c[0]).sort()).toEqual([
      'episodes',
      'items',
      'mentions',
      'recos',
      'sources',
    ]);
  });

  it('met les collections à plat : source, épisode, reco, item, mention', async () => {
    collections({
      sources: [{ id: 'ubm', data: { title: 'Un Bon Moment', theme: { colors: { accent: '#ff0066', bg: '#101010' } } } }],
      episodes: [{ data: { guid: 'ep-1', sourceId: { id: 'ubm' }, title: 'Titre', number: 3, season: 6 } }],
      recos: [{ data: { id: 'r1', status: 'validated', sourceId: { id: 'ubm' }, episodeGuid: 'ep-1', title: 'Bref' } }],
      // L'identifiant d'entrée d'un item porte sa source : `<source>/<id>`.
      items: [{ id: 'ubm/f1', data: { id: 'f1', title: 'Bref', types: ['serie'], creator: 'Kyan Khojandi' } }],
      mentions: [
        { data: { id: 'm1', itemId: 'f1', kind: 'reco', status: 'validated', sourceRef: { sourceId: 'ubm', episodeGuid: 'ep-1' } } },
        { data: { id: 'm2', itemId: 'f1', kind: 'citation', status: 'validated', sourceRef: { sourceId: 'ubm', episodeGuid: 'ep-1' } } },
      ],
    });
    const all = await paths();
    const slugs = all.map((p) => p.params.slug);

    expect(slugs).toContain('ubm');
    expect(slugs).toContain('ubm/episode/ep-1');
    expect(slugs).toContain('ubm/galerie/series');
    expect(slugs).toContain('ubm/oeuvre/f1');
    expect(all.find((p) => p.params.slug === 'ubm')?.props).toMatchObject({ accent: '#ff0066', bg: '#101010' });
    expect(all.find((p) => p.params.slug === 'ubm/episode/ep-1')?.props).toMatchObject({ repere: 'S6·E3', chiffre: 1 });
  });
});

describe('getStaticPaths — slugs URL-safe', () => {
  function avecGuid(guid: string) {
    collections({
      sources: [{ id: 'ubm', data: { title: 'Un Bon Moment' } }],
      episodes: [{ data: { guid, sourceId: { id: 'ubm' }, title: 'X' } }],
      recos: [{ data: { id: 'r1', status: 'validated', sourceId: { id: 'ubm' }, episodeGuid: guid, title: 'Y' } }],
    });
  }

  it('GARDE la casse : la page réclame sa carte avec le guid brut', async () => {
    avecGuid('yt-7kh5yi46Xh8');
    const slugs = (await paths()).map((p) => p.params.slug);
    expect(slugs).toContain('ubm/episode/yt-7kh5yi46Xh8');
  });

  it('remplace les caractères hors URL, tirets compressés', async () => {
    avecGuid('Épisode #42 / Spécial !!');
    const card = (await paths()).find((p) => p.params.slug.includes('/episode/'));
    // Le « / » du guid ne crée pas de dossier : il devient un tiret.
    expect(card?.params.slug).toBe('ubm/episode/-pisode-42-Sp-cial-');
    expect(card?.params.slug).toMatch(/^[A-Za-z0-9_/-]+$/);
  });
});

describe('GET — rendu de la carte', () => {
  it('délègue les props à renderOG et renvoie un PNG', async () => {
    const { GET } = await loadRoute();
    const props = { gabarit: 'etiquette', chiffre: 14, chiffreLibelle: 'mentions', rubrique: 'Série', titre: 'Bref' };
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
