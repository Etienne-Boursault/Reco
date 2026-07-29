/**
 * tests/search-frontend/test_search_branches_cov.test.ts — Branches restantes
 * de `src/lib/search/build-index.ts` et `src/lib/search/client.ts`.
 *
 * NB `client.ts` : `createSearchIndex()` est appelé sur `data.docs` issu d'un
 * `fetch('/search.json').json()` (cf. `SearchPalette.astro`, `recherche.astro`)
 * — aucune validation runtime. Les gardes `?? ''` de `toHit()` protègent donc
 * un index JSON réellement incomplet (ancienne version, fichier tronqué), ce
 * qu'on simule ici par un cast explicite.
 */
import { describe, it, expect } from 'vitest';
import { buildSearchIndex } from '../../src/lib/search/build-index';
import { createSearchIndex, searchGrouped } from '../../src/lib/search/client';
import type { SearchDoc } from '../../src/lib/search/types';

const sources = [{ id: 'ubm', title: 'Un Bon Moment' }];

describe('buildSearchIndex — chemins de rejet', () => {
  it('mention pointant vers un item inconnu → aucun doc item', () => {
    const out = buildSearchIndex({
      sources,
      episodes: [],
      items: [{ id: 'i1', title: 'A', types: ['film'] }],
      mentions: [{ itemId: 'fantome', sourceId: 'ubm' }],
    });
    expect(out.docs).toEqual([]);
    expect(out.count).toBe(0);
  });

  it('épisode sans champ `guests` → aucun doc invité', () => {
    const out = buildSearchIndex({
      sources,
      episodes: [{ guid: 'g1', title: 'Ép 1', sourceId: 'ubm' }],
      items: [],
      mentions: [],
    });
    expect(out.docs.map((d) => d.kind)).toEqual(['episode']);
  });

  it('nom d invité non-sluggable → ignoré, les autres passent', () => {
    const out = buildSearchIndex({
      sources,
      episodes: [{ guid: 'g1', title: 'Ép 1', sourceId: 'ubm', guests: ['???', 'Alice'] }],
      items: [],
      mentions: [],
    });
    const guests = out.docs.filter((d) => d.kind === 'guest');
    expect(guests.map((g) => g.title)).toEqual(['Alice']);
  });

  it('même invité sur deux épisodes → un seul doc invité', () => {
    const out = buildSearchIndex({
      sources,
      episodes: [
        { guid: 'g1', title: 'Ép 1', sourceId: 'ubm', guests: ['Alice'] },
        { guid: 'g2', title: 'Ép 2', sourceId: 'ubm', guests: ['Alice'] },
      ],
      items: [],
      mentions: [],
    });
    expect(out.docs.filter((d) => d.kind === 'guest')).toHaveLength(1);
  });
});

describe('searchGrouped — index JSON incomplet', () => {
  it('doc sans `source` → hit.source undefined', () => {
    const docs: SearchDoc[] = [
      { id: 'item:x', kind: 'item', title: 'Parasite', url: '/x/oeuvre/parasite' },
    ];
    const hits = searchGrouped(createSearchIndex(docs), 'parasite');
    expect(hits.items).toHaveLength(1);
    expect(hits.items[0].source).toBeUndefined();
    expect(hits.items[0].url).toBe('/x/oeuvre/parasite');
  });

  it('doc sans `url` ni `title` stockés → chaînes vides plutôt que "undefined"', () => {
    // Simule un `/search.json` d'une version antérieure du schéma.
    const docs = [
      { id: 'item:y', kind: 'item', subtitle: 'Bong Joon-ho' },
    ] as unknown as SearchDoc[];
    const hits = searchGrouped(createSearchIndex(docs), 'bong');
    expect(hits.items).toHaveLength(1);
    expect(hits.items[0].title).toBe('');
    expect(hits.items[0].url).toBe('');
  });

  it('requête vide → aucun résultat, aucun appel à MiniSearch', () => {
    const docs: SearchDoc[] = [
      { id: 'item:x', kind: 'item', title: 'Parasite', url: '/u' },
    ];
    expect(searchGrouped(createSearchIndex(docs), '   ')).toEqual({
      items: [],
      episodes: [],
      guests: [],
      total: 0,
    });
  });
});
