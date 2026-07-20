/**
 * Tests pour `src/lib/search/build-index.ts`.
 *
 * On exerce la construction de docs `item`, `episode`, `guest` depuis des
 * collections in-memory, et on vérifie le filtrage (status discarded,
 * source inconnue, déduplication invités).
 */
import { describe, it, expect } from 'vitest';
import {
  buildSearchIndex,
  episodeToDoc,
  guestToDoc,
  itemToDoc,
  type EpisodeLike,
  type ItemLike,
  type MentionLike,
  type SourceLike,
} from '../../src/lib/search/build-index';
import { SEARCH_INDEX_VERSION } from '../../src/lib/search/types';

const sources: SourceLike[] = [{ id: 'un-bon-moment', title: 'Un Bon Moment' }];

const episodes: EpisodeLike[] = [
  {
    guid: 'ep-1',
    sourceId: 'un-bon-moment',
    title: 'Avec Pierre Niney',
    guests: ['Pierre Niney'],
    number: 1,
  },
  {
    guid: 'ep-2',
    sourceId: 'un-bon-moment',
    title: 'Avec Pierre Niney encore',
    guests: ['Pierre Niney'], // doublon, doit être dédupliqué
    number: 2,
  },
  {
    guid: 'ep-3',
    sourceId: 'inconnue',
    title: 'Source inconnue',
    guests: [],
  },
];

const items: ItemLike[] = [
  { id: 'parasite', title: 'Parasite', types: ['film'], creator: 'Bong Joon-ho' },
  { id: 'kaamelott', title: 'Kaamelott', types: ['serie'], creator: null },
  { id: 'orphan', title: 'Orphelin', types: ['livre'] },
];

const mentions: MentionLike[] = [
  { itemId: 'parasite', sourceId: 'un-bon-moment', status: 'validated' },
  { itemId: 'kaamelott', sourceId: 'un-bon-moment', status: 'draft' },
  { itemId: 'parasite', sourceId: 'un-bon-moment', status: 'discarded' }, // filtré
  { itemId: 'orphan', sourceId: 'inexistante', status: 'validated' }, // filtré (source inconnue)
];

describe('itemToDoc', () => {
  it('produit une URL /<source>/oeuvre/<id> et stocke types dans text', () => {
    const doc = itemToDoc(
      { id: 'parasite', title: 'Parasite', types: ['film'], creator: 'Bong Joon-ho' },
      'un-bon-moment',
    );
    expect(doc.kind).toBe('item');
    expect(doc.url).toBe('/un-bon-moment/oeuvre/parasite');
    expect(doc.subtitle).toBe('Bong Joon-ho');
    expect(doc.text).toBe('film');
    expect(doc.source).toBe('un-bon-moment');
    expect(doc.id).toBe('item:un-bon-moment:parasite');
  });
});

describe('episodeToDoc', () => {
  it('inclut les invités dans le champ text', () => {
    const doc = episodeToDoc({
      guid: 'g1',
      sourceId: 's',
      title: 'Hello',
      guests: ['Alice', 'Bob'],
      number: 5,
    });
    expect(doc.url).toBe('/s/episode/g1');
    expect(doc.text).toBe('Alice Bob');
    expect(doc.subtitle).toBe('Épisode 5');
  });

  it('text undefined si pas d’invités', () => {
    expect(episodeToDoc({ guid: 'g', sourceId: 's', title: 'T' }).text).toBeUndefined();
  });
});

describe('guestToDoc', () => {
  it('slugifie le nom et compose une URL /<source>/invite/<slug>', () => {
    const doc = guestToDoc('Bong Joon-ho', 's');
    expect(doc?.url).toBe('/s/invite/bong-joon-ho');
    expect(doc?.id).toBe('guest:s:bong-joon-ho');
  });

  it('retourne null si le slug est vide', () => {
    expect(guestToDoc('', 's')).toBeNull();
    expect(guestToDoc('!!!', 's')).toBeNull();
  });
});

describe('buildSearchIndex', () => {
  it('produit version, count cohérent avec docs', () => {
    const idx = buildSearchIndex({
      sources,
      episodes,
      items,
      mentions,
      generatedAt: '2026-01-01T00:00:00Z',
    });
    expect(idx.version).toBe(SEARCH_INDEX_VERSION);
    expect(idx.generatedAt).toBe('2026-01-01T00:00:00Z');
    expect(idx.count).toBe(idx.docs.length);
  });

  it('filtre les mentions discarded et les sources inconnues', () => {
    const idx = buildSearchIndex({ sources, episodes, items, mentions });
    const itemDocs = idx.docs.filter((d) => d.kind === 'item');
    const ids = itemDocs.map((d) => d.id).sort();
    // parasite reste (au moins une mention validated) ; kaamelott reste (draft) ;
    // orphan filtré (source inconnue).
    expect(ids).toEqual([
      'item:un-bon-moment:kaamelott',
      'item:un-bon-moment:parasite',
    ]);
  });

  it('dédoublonne les invités par (source, slug)', () => {
    const idx = buildSearchIndex({ sources, episodes, items, mentions });
    const guests = idx.docs.filter((d) => d.kind === 'guest');
    expect(guests).toHaveLength(1);
    expect(guests[0].url).toBe('/un-bon-moment/invite/pierre-niney');
  });

  it('ignore les épisodes dont la source est inconnue', () => {
    const idx = buildSearchIndex({ sources, episodes, items, mentions });
    const eps = idx.docs.filter((d) => d.kind === 'episode');
    expect(eps.every((d) => d.source === 'un-bon-moment')).toBe(true);
    expect(eps).toHaveLength(2);
  });
});
