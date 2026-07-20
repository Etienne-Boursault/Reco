/**
 * Tests pour `src/lib/search/normalize.ts`.
 */
import { describe, it, expect } from 'vitest';
import { normalizeTerm, stripDiacritics, tokenizeFR } from '../../src/lib/search/normalize';

describe('stripDiacritics', () => {
  it('retire les accents (NFD)', () => {
    expect(stripDiacritics('Kaâmelott')).toBe('Kaamelott');
    expect(stripDiacritics('Étienne')).toBe('Etienne');
    expect(stripDiacritics('Parásite')).toBe('Parasite');
  });

  it('laisse intactes les chaînes sans accent', () => {
    expect(stripDiacritics('Parasite')).toBe('Parasite');
  });
});

describe('normalizeTerm', () => {
  it('lowercase + strip diacritics', () => {
    expect(normalizeTerm('Kaâmelott')).toBe('kaamelott');
    expect(normalizeTerm('Bong Joon-ho')).toBe('bong joon-ho');
  });
});

describe('tokenizeFR', () => {
  it('découpe sur non-alphanum, retire accents', () => {
    expect(tokenizeFR('Bong Joon-ho')).toEqual(['bong', 'joon', 'ho']);
    expect(tokenizeFR('  Kaâmelott! ')).toEqual(['kaamelott']);
    expect(tokenizeFR("L'Étranger")).toEqual(['l', 'etranger']);
  });

  it('retourne tableau vide pour entrée vide', () => {
    expect(tokenizeFR('')).toEqual([]);
  });
});
