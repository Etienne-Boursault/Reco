/**
 * Tests de `src/lib/episode/chapitres.ts` — le découpage des recos d'un
 * épisode en moments de l'écoute (direction « Les chapitres », 2026-10-07).
 */
import { describe, expect, it } from 'vitest';

import {
  decouperEnMoments,
  minutageCourt,
  secondesStrictes,
  titreDuMoment,
} from '../../src/lib/episode/chapitres';

const r = (timestamp?: string | null, id = timestamp ?? 'x') => ({ id, timestamp });

describe('secondesStrictes', () => {
  it('lit un hh:mm:ss complet', () => {
    expect(secondesStrictes('01:11:58')).toBe(4318);
    expect(secondesStrictes('00:05:03')).toBe(303);
  });

  it('refuse le mm:ss, ambigu, et tout format inattendu', () => {
    expect(secondesStrictes('11:12')).toBeNull();
    expect(secondesStrictes('00:61:00')).toBeNull();
    expect(secondesStrictes('')).toBeNull();
    expect(secondesStrictes(null)).toBeNull();
  });
});

describe('minutageCourt', () => {
  it('écrit les heures seulement quand il y en a', () => {
    expect(minutageCourt(4318)).toBe('1:11:58');
    expect(minutageCourt(303)).toBe('5:03');
  });
});

describe('decouperEnMoments', () => {
  it('sépare les moments aux creux de douze minutes ou plus', () => {
    const m = decouperEnMoments(
      [r('00:05:03'), r('00:07:01'), r('00:44:12'), r('01:10:02'), r('01:12:00')],
      4811,
    )!;
    expect(m.map((x) => x.recos.length)).toEqual([2, 1, 2]);
    expect(m[0]!.creuxApresMin).toBe(37);
    expect(m[1]!.creuxApresMin).toBe(25);
    expect(m[2]!.creuxApresMin).toBeNull();
  });

  it('un écart de 11 min 59 s reste dans le même moment, 12 min sépare', () => {
    expect(decouperEnMoments([r('00:00:01'), r('00:12:00')], 3600)!).toHaveLength(1);
    expect(decouperEnMoments([r('00:00:00'), r('00:12:00')], 3600)!).toHaveLength(2);
  });

  it('trie par minutage, quel que soit l’ordre reçu', () => {
    const m = decouperEnMoments([r('00:30:00', 'b'), r('00:02:00', 'a')], 3600)!;
    expect(m.flatMap((x) => x.recos.map((y) => y.reco.id))).toEqual(['a', 'b']);
  });

  it('renonce si une reco n’a pas de minutage', () => {
    expect(decouperEnMoments([r('00:05:00'), r(null)], 3600)).toBeNull();
  });

  it('renonce devant un minutage mm:ss', () => {
    expect(decouperEnMoments([r('00:05:00'), r('11:12')], 3600)).toBeNull();
  });

  it('renonce devant un minutage au-delà de la durée (hh:mm lu en heures)', () => {
    expect(decouperEnMoments([r('00:05:00'), r('11:12:00')], 4811)).toBeNull();
  });

  it('renonce sous deux recos', () => {
    expect(decouperEnMoments([r('00:05:00')], 3600)).toBeNull();
    expect(decouperEnMoments([], 3600)).toBeNull();
  });

  it('sans durée connue, le dernier minutage en tient lieu', () => {
    const m = decouperEnMoments([r('00:01:00'), r('00:40:00')], undefined)!;
    expect(m).toHaveLength(2);
    expect(m[1]!.titre).toBe('La dernière minute');
  });

  it('écrit la plage du moment', () => {
    const m = decouperEnMoments([r('00:05:03'), r('00:12:01'), r('00:59:00')], 3600)!;
    expect(m[0]!.plage).toBe('5:03 → 12:01');
    expect(m[1]!.plage).toBe('59:00');
  });
});

describe('titreDuMoment', () => {
  it('nomme le début, le milieu et la fin de l’écoute', () => {
    expect(titreDuMoment(303, 1201, 4811, 3, 0)).toBe('Les 21 premières minutes');
    expect(titreDuMoment(2652, 3294, 4811, 3, 1)).toBe('Au milieu de l’épisode');
    expect(titreDuMoment(4202, 4674, 4811, 3, 2)).toBe('Les 11 dernières minutes');
  });

  it('dit « le dernier quart d’heure » quand c’en est un', () => {
    expect(titreDuMoment(3900, 4700, 4811, 2, 1)).toBe('Le dernier quart d’heure');
  });

  it('un seul moment couvre tout l’épisode', () => {
    expect(titreDuMoment(10, 4000, 4811, 1, 0)).toBe('Au fil de l’épisode');
  });

  it('ailleurs, situe le moment par sa minute centrale', () => {
    expect(titreDuMoment(1200, 1300, 4811, 3, 1)).toBe('Vers la 21e minute');
  });
});
