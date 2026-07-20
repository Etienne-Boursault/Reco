/**
 * Tests pour `src/lib/stats/slug.ts`.
 */
import { describe, expect, it } from 'vitest';
import { frSortKey, hashSlug, slugify, uniqueSlug } from '../../src/lib/stats/slug';

describe('slugify (stats)', () => {
  it('met en minuscule ASCII', () => {
    expect(slugify('Alice')).toBe('alice');
  });

  it('retire les diacritiques', () => {
    expect(slugify('Mary-Léa Dupont')).toBe('mary-lea-dupont');
    expect(slugify('Éléonore')).toBe('eleonore');
  });

  it('regroupe les non-alphanum en tirets', () => {
    expect(slugify('A & B')).toBe('a-b');
  });

  it("renvoie 'x' pour entrée vide ou exotique", () => {
    expect(slugify('')).toBe('x');
    expect(slugify('---')).toBe('x');
    expect(slugify('💥')).toBe('x');
  });
});

describe('frSortKey (H26-2)', () => {
  it('normalise NFKD + lowercase pour un tri déterministe', () => {
    expect(frSortKey('Éléonore')).toBe('eleonore');
    expect(frSortKey('ZÉBRE')).toBe('zebre');
  });

  it('garde la ligature Œ (non décomposée par NFKD)', () => {
    // Cohérent Python : `unicodedata.normalize("NFKD", "Œ")` == "Œ".
    expect(frSortKey('Œuvre')).toBe('œuvre');
    expect(frSortKey('OEuvre')).toBe('oeuvre');
  });
});

describe('hashSlug (H26-3/H26-4)', () => {
  it('produit un hash stable et reproductible', () => {
    expect(hashSlug('podcasts')).toBe(hashSlug('podcasts'));
    expect(hashSlug('podcasts')).not.toBe(hashSlug('épisodes'));
  });

  it('ne contient que [0-9a-z] (base36) et est non vide', () => {
    expect(hashSlug('Stat Chart Title')).toMatch(/^[0-9a-z]+$/);
  });
});

describe('uniqueSlug (M26-19)', () => {
  it('renvoie le slug brut au premier appel', () => {
    const used = new Set<string>();
    expect(uniqueSlug('Léa Martin', used)).toBe('lea-martin');
  });

  it('suffixe -2, -3… en cas de collision', () => {
    const used = new Set<string>();
    expect(uniqueSlug('Léa Martin', used)).toBe('lea-martin');
    expect(uniqueSlug('Lea-Martin', used)).toBe('lea-martin-2');
    expect(uniqueSlug('lea martin', used)).toBe('lea-martin-3');
  });

  it("incrémente même quand un suffix existe déjà", () => {
    const used = new Set<string>(['x', 'x-2']);
    expect(uniqueSlug('X', used)).toBe('x-3');
  });
});
