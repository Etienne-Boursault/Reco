/**
 * Tests pour `src/lib/gallery/slug.ts`.
 */
import { describe, it, expect } from 'vitest';
import { slugify, buildGuestIndex } from '../../src/lib/gallery/slug';

describe('slugify', () => {
  it('met en minuscules + remplace espaces par tirets', () => {
    expect(slugify('Bong Joon-ho')).toBe('bong-joon-ho');
  });

  it("retire les accents (décomposition NFD)", () => {
    expect(slugify('Étienne Daho')).toBe('etienne-daho');
    expect(slugify('Pénélope Cruz')).toBe('penelope-cruz');
    expect(slugify('Çağatay')).toBe('cagatay');
  });

  it("remplace l'apostrophe et la ponctuation par tiret", () => {
    expect(slugify("Jean-Marc d'Or")).toBe('jean-marc-d-or');
    expect(slugify('A.B.C.')).toBe('a-b-c');
  });

  it('compresse les tirets consécutifs et trim', () => {
    expect(slugify('  --hello---world--  ')).toBe('hello-world');
  });

  it('retourne vide si entrée nulle/vide/non alphanumérique', () => {
    expect(slugify(null)).toBe('');
    expect(slugify(undefined)).toBe('');
    expect(slugify('')).toBe('');
    expect(slugify('   ')).toBe('');
    expect(slugify('???')).toBe('');
  });

  it('supporte unicode étendu (CJK décomposable indisponible → vide)', () => {
    // Caractères CJK : pas d'équivalent ASCII → remplacés par tirets → vide
    expect(slugify('王力宏')).toBe('');
    // Mixte : on garde l'ASCII utilisable
    expect(slugify('Wang 王 Hong')).toBe('wang-hong');
  });

  it('cas connu KyanKhojandi (mapping projet)', () => {
    expect(slugify('Kyan Khojandi')).toBe('kyan-khojandi');
  });
});

describe('buildGuestIndex', () => {
  it('mappe slug → nom canonique (premier vu gagne)', () => {
    const idx = buildGuestIndex(['Bong Joon-ho', 'Etienne Daho']);
    expect(idx.get('bong-joon-ho')).toBe('Bong Joon-ho');
    expect(idx.get('etienne-daho')).toBe('Etienne Daho');
  });

  it('ignore les entrées qui slugifient en vide', () => {
    const idx = buildGuestIndex(['', '???', 'Réel']);
    expect(idx.size).toBe(1);
    expect(idx.get('reel')).toBe('Réel');
  });

  it('déduplique sur collision (premier nom rencontré gagne)', () => {
    const idx = buildGuestIndex(['Étienne', 'Etienne']);
    expect(idx.size).toBe(1);
    expect(idx.get('etienne')).toBe('Étienne');
  });
});
