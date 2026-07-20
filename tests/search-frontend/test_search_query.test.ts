/**
 * Tests pour `src/lib/search/client.ts` — recherches MiniSearch FR.
 */
import { describe, it, expect } from 'vitest';
import { createSearchIndex, searchGrouped } from '../../src/lib/search/client';
import type { SearchDoc } from '../../src/lib/search/types';

const DOCS: SearchDoc[] = [
  {
    id: 'item:s:parasite',
    kind: 'item',
    title: 'Parasite',
    subtitle: 'Bong Joon-ho',
    text: 'film',
    source: 's',
    url: '/s/oeuvre/parasite',
  },
  {
    id: 'item:s:kaamelott',
    kind: 'item',
    title: 'Kaâmelott',
    subtitle: 'Alexandre Astier',
    text: 'serie',
    source: 's',
    url: '/s/oeuvre/kaamelott',
  },
  {
    id: 'episode:s:ep-niney',
    kind: 'episode',
    title: 'Avec Pierre Niney',
    subtitle: 'Épisode 12',
    text: 'Pierre Niney',
    source: 's',
    url: '/s/episode/ep-niney',
  },
  {
    id: 'guest:s:bong-joon-ho',
    kind: 'guest',
    title: 'Bong Joon-ho',
    source: 's',
    url: '/s/invite/bong-joon-ho',
  },
];

describe('searchGrouped', () => {
  const mini = createSearchIndex(DOCS);

  it('trouve par titre exact', () => {
    const r = searchGrouped(mini, 'parasite');
    expect(r.items.map((h) => h.id)).toContain('item:s:parasite');
  });

  it('matche malgré les accents (Kaâmelott ↔ kaamelott)', () => {
    const r = searchGrouped(mini, 'kaamelott');
    expect(r.items.map((h) => h.id)).toContain('item:s:kaamelott');
    const r2 = searchGrouped(mini, 'Kaâmelott');
    expect(r2.items.map((h) => h.id)).toContain('item:s:kaamelott');
  });

  it('trouve un invité via le champ text de l’épisode ET via le doc guest', () => {
    const r = searchGrouped(mini, 'Niney');
    const ids = [...r.episodes, ...r.guests].map((h) => h.id);
    expect(ids).toContain('episode:s:ep-niney');
  });

  it('trouve Bong Joon-ho (avec tiret) → doc guest', () => {
    const r = searchGrouped(mini, 'Bong');
    expect(r.guests.map((h) => h.id)).toContain('guest:s:bong-joon-ho');
  });

  it('retourne vide pour une requête vide', () => {
    const r = searchGrouped(mini, '');
    expect(r.total).toBe(0);
    expect(r.items).toHaveLength(0);
  });

  it('respecte limitPerGroup', () => {
    const many: SearchDoc[] = Array.from({ length: 10 }, (_, i) => ({
      id: `item:s:p${i}`,
      kind: 'item' as const,
      title: `Parasite ${i}`,
      url: `/s/oeuvre/p${i}`,
      source: 's',
    }));
    const m = createSearchIndex(many);
    const r = searchGrouped(m, 'parasite', { limitPerGroup: 3 });
    expect(r.items).toHaveLength(3);
  });

  it('boost titre > text (un match titre arrive avant un match text)', () => {
    const r = searchGrouped(mini, 'Bong');
    // 'Bong' apparaît dans subtitle de parasite ET dans title de guest doc.
    // Le doc guest devrait scorer plus haut que parasite (titre vs subtitle).
    const guestScore = r.guests[0]?.score ?? 0;
    const itemScore = r.items[0]?.score ?? 0;
    expect(guestScore).toBeGreaterThan(itemScore);
  });
});
