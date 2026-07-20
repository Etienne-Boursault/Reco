/**
 * Tests trending badge — ≥2 mentions visibles dans la fenêtre des
 * `windowMonths` derniers mois.
 */
import { describe, it, expect } from 'vitest';
import { isTrending, type JoinedMention } from '../../src/lib/work/aggregator';

function jm(date?: string): JoinedMention {
  return {
    mention: {
      id: 'm',
      itemId: 'i',
      sourceRef: { sourceId: 's', episodeGuid: 'g' },
      kind: 'reco',
      status: 'validated',
    },
    episode: { guid: 'g', title: 't', date: date ? new Date(date) : undefined },
  };
}

describe('isTrending', () => {
  const now = new Date('2026-06-01');

  it('false si <2 mentions', () => {
    expect(isTrending([jm('2026-05-01')], now)).toBe(false);
  });

  it('true si 2 mentions dans les 12 derniers mois', () => {
    expect(isTrending([jm('2025-10-01'), jm('2026-04-01')], now)).toBe(true);
  });

  it('false si mentions hors fenêtre', () => {
    expect(isTrending([jm('2020-01-01'), jm('2021-01-01')], now)).toBe(false);
  });

  it('true si exactement 2 mentions à la frontière', () => {
    expect(isTrending([jm('2025-06-02'), jm('2026-05-31')], now)).toBe(true);
  });

  it('ignore mentions sans date pour la fenêtre temporelle', () => {
    expect(isTrending([jm(), jm()], now)).toBe(false);
  });

  it('respecte windowMonths personnalisé', () => {
    // 3 mois → 2024-10 hors fenêtre
    expect(isTrending([jm('2025-10-01'), jm('2026-04-01')], now, 3)).toBe(false);
    // 12 mois → ok
    expect(isTrending([jm('2025-10-01'), jm('2026-04-01')], now, 12)).toBe(true);
  });
});
