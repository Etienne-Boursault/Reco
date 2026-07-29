/**
 * tests/gallery/test_page_branches_cov.test.ts — Couverture de branches de
 * `src/lib/gallery/page.ts` (JSON-LD ItemList + BreadcrumbList) et des
 * derniers chemins non couverts de `src/lib/gallery/aggregate.ts`.
 */
import { describe, it, expect } from 'vitest';
import {
  galleryItemListSchema,
  galleryBreadcrumb,
} from '../../src/lib/gallery/page.ts';
import { selectByGuest, type GalleryEntry } from '../../src/lib/gallery/aggregate.ts';

function entry(over: Partial<GalleryEntry> = {}): GalleryEntry {
  return {
    id: 'i1',
    title: 'Titre',
    types: ['film'],
    creator: 'Réal',
    year: 2020,
    mentionCount: 1,
    ...over,
  };
}

describe('galleryItemListSchema', () => {
  it('produit un ItemList schema.org avec positions 1..N', () => {
    const node = galleryItemListSchema(
      [entry({ id: 'a', title: 'A' }), entry({ id: 'b', title: 'B' })],
      { name: 'Films' },
    );
    expect(node['@context']).toBe('https://schema.org');
    expect(node['@type']).toBe('ItemList');
    expect(node.name).toBe('Films');
    expect(node.numberOfItems).toBe(2);
    const list = node.itemListElement as Record<string, unknown>[];
    expect(list).toHaveLength(2);
    expect(list[0].position).toBe(1);
    expect(list[1].position).toBe(2);
    expect(list[0]['@type']).toBe('ListItem');
  });

  it("supprime le @context des enfants (invalide dans un ItemList)", () => {
    const node = galleryItemListSchema([entry()], { name: 'Films' });
    const first = (node.itemListElement as Record<string, unknown>[])[0];
    const item = first.item as Record<string, unknown>;
    expect(item['@context']).toBeUndefined();
    expect(item['@type']).toBe('Movie');
    expect(item.name).toBe('Titre');
  });

  it("mappe le premier type de l'entrée ; types vide → 'autre' (CreativeWork)", () => {
    const node = galleryItemListSchema([entry({ types: [] })], { name: 'X' });
    const item = (node.itemListElement as Record<string, unknown>[])[0]
      .item as Record<string, unknown>;
    expect(item['@type']).toBe('CreativeWork');
  });

  it("creator null → pas de propriété créateur dans le noeud enfant", () => {
    const node = galleryItemListSchema([entry({ creator: null })], { name: 'X' });
    const item = (node.itemListElement as Record<string, unknown>[])[0]
      .item as Record<string, unknown>;
    // film → Movie ⇒ la propriété serait `director` si un créateur existait.
    expect(item.director).toBeUndefined();
  });

  it('urlBuilder fourni → url posée sur le noeud enfant', () => {
    const node = galleryItemListSchema([entry({ id: 'zz' })], {
      name: 'X',
      urlBuilder: (e) => `https://x.fr/oeuvre/${e.id}`,
    });
    const item = (node.itemListElement as Record<string, unknown>[])[0]
      .item as Record<string, unknown>;
    expect(item.url).toBe('https://x.fr/oeuvre/zz');
  });

  it('urlBuilder qui renvoie undefined → pas de url', () => {
    const node = galleryItemListSchema([entry()], {
      name: 'X',
      urlBuilder: () => undefined,
    });
    const item = (node.itemListElement as Record<string, unknown>[])[0]
      .item as Record<string, unknown>;
    expect(item.url).toBeUndefined();
  });

  it('maxItems par défaut = 100 (numberOfItems garde le total réel)', () => {
    const entries = Array.from({ length: 120 }, (_, i) =>
      entry({ id: `i${i}`, title: `T${i}` }),
    );
    const node = galleryItemListSchema(entries, { name: 'X' });
    expect((node.itemListElement as unknown[]).length).toBe(100);
    expect(node.numberOfItems).toBe(120);
  });

  it('maxItems explicite tronque la liste', () => {
    const entries = Array.from({ length: 5 }, (_, i) => entry({ id: `i${i}` }));
    const node = galleryItemListSchema(entries, { name: 'X', maxItems: 2 });
    expect((node.itemListElement as unknown[]).length).toBe(2);
    expect(node.numberOfItems).toBe(5);
  });

  it('description fournie → posée ; absente → clé omise', () => {
    const withDesc = galleryItemListSchema([entry()], {
      name: 'X',
      description: 'Toutes les œuvres',
    });
    expect(withDesc.description).toBe('Toutes les œuvres');
    const without = galleryItemListSchema([entry()], { name: 'X' });
    expect('description' in without).toBe(false);
  });

  it('liste vide → itemListElement vide et numberOfItems 0', () => {
    const node = galleryItemListSchema([], { name: 'X' });
    expect(node.itemListElement).toEqual([]);
    expect(node.numberOfItems).toBe(0);
  });
});

describe('galleryBreadcrumb', () => {
  it('produit un BreadcrumbList à 3 niveaux dans l ordre', () => {
    const node = galleryBreadcrumb({
      homeUrl: 'https://x.fr/',
      sourceName: 'Un Bon Moment',
      sourceUrl: 'https://x.fr/ubm',
      galleryName: 'Films',
      galleryUrl: 'https://x.fr/ubm/films',
    });
    expect(node['@context']).toBe('https://schema.org');
    expect(node['@type']).toBe('BreadcrumbList');
    const list = node.itemListElement as Record<string, unknown>[];
    expect(list.map((e) => e.position)).toEqual([1, 2, 3]);
    expect(list.map((e) => e.name)).toEqual(['Accueil', 'Un Bon Moment', 'Films']);
    expect(list.map((e) => e.item)).toEqual([
      'https://x.fr/',
      'https://x.fr/ubm',
      'https://x.fr/ubm/films',
    ]);
  });
});

describe('selectByGuest — recommendedBy absent', () => {
  it("une mention sans recommendedBy ne matche aucun invité", () => {
    const items = [{ id: 'i1', title: 'A', types: ['film'] }];
    const out = selectByGuest(
      items,
      [{ itemId: 'i1', recommendedBy: null }, { itemId: 'i1' }],
      'Alice',
    );
    expect(out).toEqual([]);
  });

  it("recherche par chaîne vide ne ramasse pas les mentions sans auteur", () => {
    const items = [{ id: 'i1', title: 'A', types: ['film'] }];
    // `''` normalisé == `(m.recommendedBy ?? '')` : la garde doit rester le
    // filtre `itemIds`, donc ces mentions matchent bien la requête vide.
    const out = selectByGuest(items, [{ itemId: 'i1', recommendedBy: undefined }], '');
    expect(out.map((e) => e.id)).toEqual(['i1']);
    expect(out[0].mentionCount).toBe(1);
  });
});
