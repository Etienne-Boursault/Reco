/**
 * Tests du helper de pluralisation français (src/utils/plural). N7.
 *
 * Règle : le pluriel s'applique dès n >= 2 ; 0 et 1 restent au singulier.
 */
import { describe, it, expect } from 'vitest';
import { plural } from '../../src/utils/plural';

describe('plural', () => {
  it('0 → singulier (français : 0 est singulier)', () => {
    expect(plural(0, 'recommandation')).toBe('recommandation');
  });

  it('1 → singulier', () => {
    expect(plural(1, 'recommandation')).toBe('recommandation');
  });

  it('2 → pluriel par défaut (+s)', () => {
    expect(plural(2, 'recommandation')).toBe('recommandations');
  });

  it('n grand → pluriel', () => {
    expect(plural(42, 'épisode')).toBe('épisodes');
  });

  it('accorde un participe passé (extraite/extraites)', () => {
    expect(plural(1, 'extraite')).toBe('extraite');
    expect(plural(3, 'extraite')).toBe('extraites');
  });

  it('supporte une forme plurielle irrégulière explicite', () => {
    expect(plural(1, 'travail', 'travaux')).toBe('travail');
    expect(plural(2, 'travail', 'travaux')).toBe('travaux');
  });
});
