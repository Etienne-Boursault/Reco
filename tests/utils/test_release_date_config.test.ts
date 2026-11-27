/**
 * Champ `releaseDate` de la collection `recos` (R4 B, 27/11/2026) : la date de sortie
 * annoncée d'une œuvre pas encore publiée, `AAAA-MM-JJ`, jour de calendrier réel.
 * Pendant Zod de `tools/date_sortie.py` (le validateur Python, qui ajoute l'horizon de
 * 3 ans : il dépend de l'horloge, donc pas du schéma).
 */
import { describe, it, expect } from 'vitest';
import { collections } from '../../src/content.config';

const recos = (collections.recos as unknown as {
  schema: { safeParse: (v: unknown) => { success: boolean; data?: any } };
}).schema;

const RECO_MIN = {
  id: 'ubm-3348',
  sourceId: 'ubm',
  episodeGuid: 'guid-1',
  title: '(Re)belle',
  types: ['album'],
};

describe('releaseDate de la reco', () => {
  it('est facultative', () => {
    const res = recos.safeParse(RECO_MIN);
    expect(res.success).toBe(true);
    expect(res.data.releaseDate).toBeUndefined();
  });

  it('accepte une vraie date AAAA-MM-JJ, gardée telle quelle en chaîne', () => {
    const res = recos.safeParse({ ...RECO_MIN, releaseDate: '2026-11-20' });
    expect(res.success).toBe(true);
    expect(res.data.releaseDate).toBe('2026-11-20');
  });

  it('accepte le 29 février d’une année bissextile', () => {
    expect(recos.safeParse({ ...RECO_MIN, releaseDate: '2028-02-29' }).success).toBe(true);
  });

  it.each([
    '2026-02-30', // jour inexistant
    '2027-02-29', // année non bissextile
    '2026-13-01',
    '2026-11-31',
    '20261120',
    '20/11/2026',
    '2026-1-5',
    '2026-11-20T10:00:00Z',
    '',
    'demain',
  ])('refuse « %s »', (releaseDate) => {
    expect(recos.safeParse({ ...RECO_MIN, releaseDate }).success).toBe(false);
  });

  it('refuse une valeur qui n’est pas une chaîne', () => {
    expect(recos.safeParse({ ...RECO_MIN, releaseDate: 20261120 }).success).toBe(false);
    expect(recos.safeParse({ ...RECO_MIN, releaseDate: null }).success).toBe(false);
  });
});
