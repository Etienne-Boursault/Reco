/**
 * Tests de `src/lib/gallery/sommaire.ts`.
 *
 * Le sommaire interne `/galeries` et l'onglet « Par type » du catalogue
 * annoncent les mêmes nombres : ces tests protègent ce qu'ils partagent —
 * mentions écartées ignorées, galeries vides retirées, ordre décroissant.
 */
import { describe, expect, it } from 'vitest';

import { sommaireGaleries } from '../../src/lib/gallery/sommaire';

const item = (id: string, types: string[]) => ({ id, title: id, types });
const mention = (itemId: string, status: 'validated' | 'discarded' = 'validated') => ({
  itemId,
  status,
});

describe('sommaireGaleries', () => {
  it('compte les œuvres mentionnées par galerie, la plus fournie en tête', () => {
    const s = sommaireGaleries(
      [item('f1', ['film']), item('f2', ['film']), item('s1', ['serie'])],
      [mention('f1'), mention('f2'), mention('s1')],
    );
    expect(s.map((g) => [g.slug, g.n])).toEqual([
      ['films', 2],
      ['series', 1],
    ]);
  });

  it('ignore une œuvre dont la seule mention est écartée', () => {
    const s = sommaireGaleries([item('f1', ['film'])], [mention('f1', 'discarded')]);
    expect(s).toEqual([]);
  });

  it('ignore une œuvre jamais mentionnée', () => {
    expect(sommaireGaleries([item('f1', ['film'])], [])).toEqual([]);
  });

  it('une œuvre multi-types compte dans chacune de ses galeries', () => {
    const s = sommaireGaleries([item('k', ['serie', 'film'])], [mention('k')]);
    expect(s.map((g) => g.slug).sort()).toEqual(['films', 'series']);
  });

  it('un album compte à la fois dans « Musique » et dans « Albums »', () => {
    const s = sommaireGaleries([item('a', ['album'])], [mention('a')]);
    expect(s.map((g) => g.slug).sort()).toEqual(['albums', 'musique']);
  });
});

describe('sommaireGaleries — titres d’aperçu', () => {
  it('donne les œuvres les plus citées de la galerie, trois au plus', () => {
    const s = sommaireGaleries(
      [item('a', ['film']), item('b', ['film']), item('c', ['film']), item('d', ['film'])],
      [mention('d'), mention('d'), mention('d'), mention('c'), mention('c'), mention('b'), mention('a')],
    );
    // À égalité (a et b, une mention chacun), la galerie départage par titre.
    expect(s[0]!.apercu).toEqual(['d', 'c', 'a']);
  });

  it('un titre n’apparaît que sur une carte : la galerie la plus fournie le garde', () => {
    // « k » est album ET musique : Musique (2 œuvres) passe avant Albums (1).
    const s = sommaireGaleries(
      [item('k', ['album']), item('m', ['musique'])],
      [mention('k'), mention('m')],
    );
    const musique = s.find((g) => g.slug === 'musique')!;
    const albums = s.find((g) => g.slug === 'albums')!;
    expect(musique.apercu).toEqual(['k', 'm']);
    expect(albums.apercu).toEqual([]);
  });
});
