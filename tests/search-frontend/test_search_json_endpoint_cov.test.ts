/**
 * tests/search-frontend/test_search_json_endpoint_cov.test.ts
 *
 * Endpoint `/search.json` (`src/pages/search.json.ts`).
 *
 * L'endpoint est une fine couche d'adaptation : il charge les 4 collections
 * Astro, projette chaque entrée sur la forme « Like » attendue par
 * `buildSearchIndex`, puis sérialise. On mocke donc `astro:content` à la
 * frontière et on vérifie :
 *   - les headers (Content-Type, Cache-Control 5 min) ;
 *   - que la projection préserve bien les champs (guid, guests, creator…) ;
 *   - que les champs optionnels absents deviennent `null` (et pas `undefined`).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

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

/** Contexte APIContext minimal — l'endpoint n'en lit aucun champ. */
function ctx(): Parameters<
  Awaited<typeof import('../../src/pages/search.json.js')>['GET']
>[0] {
  return {} as never;
}

async function loadRoute() {
  return await import('../../src/pages/search.json.js');
}

beforeEach(() => {
  getCollection.mockReset();
});

describe('GET /search.json', () => {
  it('émet application/json UTF-8 avec un cache 5 min', async () => {
    collections({ sources: [], episodes: [], items: [], mentions: [] });
    const { GET } = await loadRoute();
    const res = await GET(ctx());

    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('application/json; charset=utf-8');
    expect(res.headers.get('Cache-Control')).toBe('public, max-age=300, must-revalidate');
  });

  it('charge les quatre collections attendues', async () => {
    collections({ sources: [], episodes: [], items: [], mentions: [] });
    const { GET } = await loadRoute();
    await GET(ctx());

    const names = getCollection.mock.calls.map((c) => c[0]).sort();
    expect(names).toEqual(['episodes', 'items', 'mentions', 'sources']);
  });

  it('renvoie un index vide (mais structuré) sans contenu', async () => {
    collections({ sources: [], episodes: [], items: [], mentions: [] });
    const { GET } = await loadRoute();
    const body = (await (await GET(ctx())).json()) as { docs: unknown[]; version: number };

    expect(Array.isArray(body.docs)).toBe(true);
    expect(body.docs).toHaveLength(0);
    expect(typeof body.version).toBe('number');
  });

  it('projette items, épisodes et invités en documents indexables', async () => {
    collections({
      sources: [{ data: { id: 'ubm', title: 'Un Bon Moment' } }],
      episodes: [
        {
          data: {
            guid: 'ep-1',
            title: 'Épisode 1',
            sourceId: { id: 'ubm' },
            guests: ['Alice Martin'],
            number: 12,
          },
        },
      ],
      items: [
        { data: { id: 'w-1', title: 'Dune', types: ['film'], creator: 'Denis Villeneuve' } },
      ],
      mentions: [
        {
          data: {
            itemId: 'w-1',
            sourceRef: { sourceId: 'ubm' },
            recommendedBy: 'Alice Martin',
            status: 'validated',
          },
        },
      ],
    });
    const { GET } = await loadRoute();
    const body = (await (await GET(ctx())).json()) as {
      docs: Array<{ kind: string; title: string; subtitle?: string; url: string }>;
    };

    const kinds = body.docs.map((d) => d.kind);
    expect(kinds).toContain('item');
    expect(kinds).toContain('episode');
    expect(kinds).toContain('guest');

    const item = body.docs.find((d) => d.kind === 'item');
    expect(item?.title).toBe('Dune');
    // `creator` est bien transmis (projection `it.data.creator ?? null`).
    expect(item?.subtitle).toBe('Denis Villeneuve');

    const episode = body.docs.find((d) => d.kind === 'episode');
    expect(episode?.title).toBe('Épisode 1');
    expect(episode?.url).toContain('ep-1');
  });

  it('normalise number/creator/recommendedBy absents en null', async () => {
    collections({
      sources: [{ data: { id: 'ubm', title: 'Un Bon Moment' } }],
      episodes: [
        { data: { guid: 'ep-2', title: 'Sans numéro', sourceId: { id: 'ubm' } } },
      ],
      items: [{ data: { id: 'w-2', title: 'Sans créateur', types: ['livre'] } }],
      mentions: [
        {
          data: { itemId: 'w-2', sourceRef: { sourceId: 'ubm' }, status: 'validated' },
        },
      ],
    });
    const { GET } = await loadRoute();
    const body = (await (await GET(ctx())).json()) as {
      docs: Array<{ kind: string; subtitle?: string }>;
    };

    // `creator: undefined` → `null` → `subtitle` absent après sérialisation JSON.
    const item = body.docs.find((d) => d.kind === 'item');
    expect(item).toBeDefined();
    expect(item?.subtitle).toBeUndefined();
    // Aucun doc `guest` : `recommendedBy` absent et pas de `guests` sur l'épisode.
    expect(body.docs.some((d) => d.kind === 'guest')).toBe(false);
  });

  it('sérialise sans pretty-print (payload compact)', async () => {
    collections({
      sources: [{ data: { id: 'ubm', title: 'Un Bon Moment' } }],
      episodes: [],
      items: [],
      mentions: [],
    });
    const { GET } = await loadRoute();
    const text = await (await GET(ctx())).text();

    expect(text).not.toMatch(/\n\s\s/);
  });
});
