/**
 * Tests pour `src/lib/gallery/aggregate.ts`.
 */
import { describe, it, expect } from 'vitest';
import {
  countMentionsByItem,
  listGuests,
  publicMentions,
  selectByGuest,
  selectByType,
  sortGalleryEntries,
} from '../../src/lib/gallery/aggregate';

const items = [
  { id: 'a', title: 'Aardvark', types: ['film'] as const },
  { id: 'b', title: 'Belmondo', types: ['film', 'video'] as const },
  { id: 'c', title: 'Cendrillon', types: ['livre'] as const },
  { id: 'd', title: 'Dune', types: ['film', 'livre'] as const },
  { id: 'z', title: 'Zorba', types: ['film'] as const }, // 0 mention
];

const mentions = [
  { itemId: 'a', recommendedBy: 'Alice', status: 'validated' as const },
  { itemId: 'a', recommendedBy: 'Bob', status: 'validated' as const },
  { itemId: 'a', recommendedBy: 'Alice', status: 'discarded' as const }, // filtré
  { itemId: 'b', recommendedBy: 'Alice', status: 'draft' as const },
  { itemId: 'c', recommendedBy: 'Bob', status: 'validated' as const },
  { itemId: 'd', recommendedBy: 'Carol', status: 'validated' as const },
];

describe('publicMentions', () => {
  it('exclut les discarded, conserve draft + validated', () => {
    expect(publicMentions(mentions)).toHaveLength(5);
  });
});

describe('countMentionsByItem', () => {
  it('compte les mentions publiques par item', () => {
    const counts = countMentionsByItem(mentions);
    expect(counts.get('a')).toBe(2);
    expect(counts.get('b')).toBe(1);
    expect(counts.get('c')).toBe(1);
    expect(counts.get('d')).toBe(1);
  });
});

describe('selectByType', () => {
  it('inclut un item multi-types qui matche', () => {
    const films = selectByType(items, mentions, ['film']);
    const ids = films.map((e) => e.id);
    expect(ids).toContain('a');
    expect(ids).toContain('b');
    expect(ids).toContain('d'); // multi-type [film, livre]
    expect(ids).not.toContain('c');
    expect(ids).not.toContain('z'); // 0 mention
  });

  it('trie par nb mentions DESC puis titre ASC', () => {
    const films = selectByType(items, mentions, ['film']);
    expect(films[0].id).toBe('a'); // 2 mentions
    // b (1) et d (1) → tri alpha
    expect(films[1].id).toBe('b');
    expect(films[2].id).toBe('d');
  });

  it('accepte plusieurs types (musique élargi)', () => {
    const livres = selectByType(items, mentions, ['livre']);
    expect(livres.map((e) => e.id).sort()).toEqual(['c', 'd']);
  });
});

describe('selectByGuest', () => {
  it("retourne les items d'un invité (casefold + trim)", () => {
    const alice = selectByGuest(items, mentions, ' alice ');
    expect(alice.map((e) => e.id).sort()).toEqual(['a', 'b']);
  });

  it("retourne vide si invité inconnu", () => {
    expect(selectByGuest(items, mentions, 'inconnu')).toHaveLength(0);
  });

  it("ignore les mentions discarded", () => {
    const alice = selectByGuest(items, mentions, 'Alice');
    const a = alice.find((e) => e.id === 'a');
    // 1 validated + 1 discarded → mentionCount = 1 pour Alice sur 'a'
    expect(a?.mentionCount).toBe(1);
  });
});

describe('listGuests', () => {
  it('liste les invités uniques triés A→Z', () => {
    expect(listGuests(mentions)).toEqual(['Alice', 'Bob', 'Carol']);
  });

  it('exclut les hosts', () => {
    expect(listGuests(mentions, ['Alice'])).toEqual(['Bob', 'Carol']);
  });

  it('exclut les mentions sans recommendedBy', () => {
    const m = [...mentions, { itemId: 'x', recommendedBy: null }];
    expect(listGuests(m)).toEqual(['Alice', 'Bob', 'Carol']);
  });
});

describe('sortGalleryEntries (stabilité)', () => {
  it('tri locale FR (é avant f)', () => {
    const entries = [
      { id: '1', title: 'Foo', types: [], creator: null, year: null, mentionCount: 1 },
      { id: '2', title: 'Éléphant', types: [], creator: null, year: null, mentionCount: 1 },
    ];
    const sorted = sortGalleryEntries(entries);
    expect(sorted[0].title).toBe('Éléphant');
  });
});
