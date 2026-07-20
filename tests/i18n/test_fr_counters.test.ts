/**
 * Tests i18n — F-M-7 : namespace `common.counters.*` documenté + présent.
 *
 * Smoke : on vérifie que toutes les clés attendues existent et sont des
 * strings non vides. Pas de vérification de wording (sujet à évolution).
 */
import { describe, it, expect } from 'vitest';
import { fr } from '../../src/i18n/fr';

const COUNTER_KEYS = [
  'common.counters.items',
  'common.counters.mentions',
  'common.counters.episodes',
  'common.counters.guests',
  'common.counters.podcasts',
  'common.counters.uniqueWorks',
  'common.counters.uniqueGuests',
  'common.counters.recommendations',
] as const;

describe('i18n FR — common.counters.*', () => {
  it.each(COUNTER_KEYS)('clé %s existe et est non vide', (k) => {
    const v = (fr as Record<string, string>)[k];
    expect(typeof v).toBe('string');
    expect(v.length).toBeGreaterThan(0);
  });

  it('stats.empty.typeDistribution / monthly existent (F-M-5)', () => {
    expect(fr['stats.empty.typeDistribution']).toBeDefined();
    expect(fr['stats.empty.monthly']).toBeDefined();
  });
});
