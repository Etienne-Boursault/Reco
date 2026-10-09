/**
 * Page œuvre — les blocs de la direction « La récurrence » (2026-10-07) :
 * frise des mentions, « Qui en parle », mentions regroupées par année.
 *
 * Fichier séparé de `test_page_oeuvre_cov.test.ts`, qui dépasse déjà les 500
 * lignes. Même principe : `astro:content` est mocké, et la page est rendue
 * avec les props que produit son propre `getStaticPaths`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText } from '../gallery/_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

import WorkPage, { getStaticPaths } from '../../src/pages/[source]/oeuvre/[itemId].astro';

interface Entry {
  id?: string;
  data: Record<string, unknown>;
}

const SOURCE = {
  id: 'ubm',
  data: {
    id: 'ubm',
    title: 'Un Bon Moment',
    hosts: ['Kyan Khojandi', 'Navo'],
    theme: { colors: { bg: '#101010', surface: '#181818', text: '#fff', muted: '#999', accent: '#ff5500' } },
  },
};

function seed(map: Partial<Record<'sources' | 'items' | 'mentions' | 'episodes', Entry[]>>): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

const item = (id: string): Entry => ({ id: `ubm/${id}`, data: { id, title: `Titre ${id}`, types: ['serie'] } });

function mention(id: string, guid: string, over: Record<string, unknown> = {}): Entry {
  return {
    data: {
      id,
      itemId: 'w1',
      sourceRef: { sourceId: 'ubm', episodeGuid: guid },
      kind: 'reco',
      status: 'validated',
      ...over,
    },
  };
}

function episode(guid: string, iso: string, over: Record<string, unknown> = {}): Entry {
  return {
    data: { guid, sourceId: { id: 'ubm' }, title: `Épisode ${guid}`, date: new Date(`${iso}T00:00:00Z`), ...over },
  };
}

async function renderWork(): Promise<string> {
  const p = ((await getStaticPaths()) as unknown as Array<{
    params: { source: string; itemId: string };
    props: Record<string, unknown>;
  }>).find((x) => x.params.itemId === 'w1');
  if (!p) throw new Error('aucune route pour w1');
  return renderPage(WorkPage, { params: p.params, props: p.props, path: '/ubm/oeuvre/w1' });
}

/** Trois mentions sur trois années, dont une évoquée et une sans auteur. */
function seedAnnees(): void {
  seed({
    sources: [SOURCE],
    items: [item('w1')],
    mentions: [
      mention('m1', 'g1', { recommendedBy: 'Kyan Khojandi & Navo' }),
      mention('m2', 'g2', { kind: 'citation', recommendedBy: 'Kyan Khojandi' }),
      mention('m3', 'g3'),
    ],
    episodes: [
      episode('g1', '2020-03-29', { number: 10 }),
      episode('g2', '2023-11-19', { number: 56 }),
      episode('g3', '2026-05-04', { season: 5, number: 29 }),
    ],
  });
}

beforeEach(() => {
  getCollection.mockReset();
});

describe('page œuvre — la récurrence', () => {
  it('plusieurs années → une frise dont chaque point mène à son épisode', async () => {
    seedAnnees();
    const html = await renderWork();
    expect(html).toContain('class="frise"');
    expect(html.match(/class="frise-point"/g)).toHaveLength(3);
    expect(html).toContain('href="/ubm/episode/g2"');
    expect(html).toContain('aria-label="#56 · 19 novembre 2023 · évoquée"');
  });

  it('une seule année → pas de frise vide', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [mention('m1', 'g1'), mention('m2', 'g2')],
      episodes: [episode('g1', '2026-03-16'), episode('g2', '2026-05-04')],
    });
    expect(await renderWork()).not.toContain('class="frise"');
  });

  it('la période de l’en-tête : « 6 ans », de mars 2020 à mai 2026', async () => {
    seedAnnees();
    const text = visibleText(await renderWork());
    expect(text).toContain('de mars 2020 à mai 2026');
    expect(text).toContain('6 ans');
  });

  it('« Qui en parle » compte chaque voix, et les mentions sans auteur', async () => {
    seedAnnees();
    const text = visibleText(await renderWork());
    expect(text).toContain('Qui en parle');
    expect(text).toMatch(/Kyan Khojandi\s*2 mentions/);
    expect(text).toMatch(/Navo\s*1 mention/);
    expect(text).toMatch(/Sans attribution\s*1 mention/);
  });

  it('sans aucun auteur, pas de bloc « Qui en parle »', async () => {
    seed({
      sources: [SOURCE],
      items: [item('w1')],
      mentions: [mention('m1', 'g1')],
      episodes: [episode('g1', '2026-03-16')],
    });
    expect(visibleText(await renderWork())).not.toContain('Qui en parle');
  });

  it('les mentions sont regroupées par année, la plus récente d’abord', async () => {
    seedAnnees();
    const html = await renderWork();
    const annees = [...html.matchAll(/class="annee-titre"[^>]*>(\d{4})</g)].map((m) => m[1]);
    expect(annees).toEqual(['2026', '2023', '2020']);
  });
});
