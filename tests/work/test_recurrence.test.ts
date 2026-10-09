/**
 * Tests de `src/lib/work/recurrence.ts` — période, frise, « Qui en parle » et
 * regroupement par année de la fiche œuvre (direction « La récurrence »).
 */
import { describe, expect, it } from 'vitest';

import type { JoinedMention } from '../../src/lib/work/aggregator';
import {
  ECART_MIN,
  frise,
  parAnnee,
  periode,
  quiEnParle,
} from '../../src/lib/work/recurrence';

let suivant = 0;
function jm(
  iso: string | null,
  over: { kind?: 'reco' | 'citation'; by?: string | null; season?: number; number?: number } = {},
): JoinedMention {
  suivant += 1;
  return {
    mention: {
      id: `m${suivant}`,
      itemId: 'w1',
      sourceRef: { sourceId: 'ubm', episodeGuid: `ep${suivant}` },
      recommendedBy: over.by === undefined ? 'Kyan Khojandi' : over.by,
      kind: over.kind ?? 'reco',
      status: 'validated',
    },
    episode:
      iso === null
        ? { guid: `ep${suivant}`, title: 'Sans date', number: over.number, season: over.season }
        : {
            guid: `ep${suivant}`,
            title: `Épisode ${suivant}`,
            date: new Date(`${iso}T00:00:00Z`),
            number: over.number,
            season: over.season,
          },
  };
}

describe('periode', () => {
  it('plusieurs années → « N ans », de tel mois à tel mois', () => {
    const p = periode([jm('2026-05-04'), jm('2020-03-29'), jm('2023-11-19')])!;
    expect(p.chiffre).toBe('6 ans');
    expect(p.legende).toBe('de mars 2020 à mai 2026');
  });

  it('deux années civiles voisines → « 1 an »', () => {
    expect(periode([jm('2025-12-15'), jm('2026-01-12')])!.chiffre).toBe('1 an');
  });

  it('une seule année → l’année en chiffre, les mois en légende', () => {
    const p = periode([jm('2026-03-16'), jm('2026-05-04')])!;
    expect(p.chiffre).toBe('2026');
    expect(p.legende).toBe('de mars à mai 2026');
  });

  it('une seule mention → « en mai 2026 »', () => {
    expect(periode([jm('2026-05-04')])!.legende).toBe('en mai 2026');
  });

  it('aucune date → null', () => {
    expect(periode([jm(null)])).toBeNull();
  });

  it('lit les dates en UTC : un 1er janvier reste dans son année', () => {
    expect(periode([jm('2021-01-01'), jm('2020-06-01')])!.chiffre).toBe('1 an');
  });
});

describe('frise', () => {
  it('pas de frise quand tout tient dans une année, ou sans date', () => {
    expect(frise([jm('2026-03-16'), jm('2026-05-04')], 'ubm')).toBeNull();
    expect(frise([jm('2026-03-16')], 'ubm')).toBeNull();
    expect(frise([jm(null), jm(null)], 'ubm')).toBeNull();
  });

  it('une graduation par année, au milieu de l’année', () => {
    const f = frise([jm('2020-03-01'), jm('2021-09-01')], 'ubm')!;
    expect(f.annees.map((a) => a.annee)).toEqual([2020, 2021]);
    expect(f.annees[0]!.gauche).toBeCloseTo(24.9, 0);
    expect(f.annees[1]!.gauche).toBeCloseTo(74.9, 0);
  });

  it('chaque point mène à son épisode et se dit recommandé ou évoqué', () => {
    const f = frise(
      [jm('2020-03-29', { season: undefined, number: 10 }), jm('2026-05-04', { kind: 'citation', season: 5, number: 29 })],
      'ubm',
    )!;
    expect(f.points[0]!.href).toMatch(/^\/ubm\/episode\/ep\d+$/);
    expect(f.points[0]!.recommandee).toBe(true);
    expect(f.points[0]!.libelle).toBe('#10 · 29 mars 2020 · recommandée');
    expect(f.points[1]!.libelle).toBe('S5·E29 · 4 mai 2026 · évoquée');
  });

  it('deux points trop proches s’empilent, deux points éloignés partagent une rangée', () => {
    const f = frise([jm('2020-03-01'), jm('2020-04-01'), jm('2026-01-01')], 'ubm')!;
    expect(f.points.map((p) => p.voie)).toEqual([0, 1, 0]);
    expect(f.voies).toBe(2);
  });

  it('aucune paire d’une même rangée n’est plus proche que l’écart minimal', () => {
    const dates = ['2020-03-29', '2020-04-12', '2020-04-26', '2020-11-01', '2021-02-07',
      '2021-03-07', '2021-11-25', '2022-09-19', '2023-11-19', '2025-12-08', '2025-12-15',
      '2026-01-12', '2026-03-16', '2026-05-04'];
    const f = frise(dates.map((d) => jm(d)), 'ubm')!;
    for (let v = 0; v < f.voies; v += 1) {
      const xs = f.points.filter((p) => p.voie === v).map((p) => p.gauche / 100);
      for (let i = 1; i < xs.length; i += 1) {
        expect(xs[i]! - xs[i - 1]!).toBeGreaterThanOrEqual(ECART_MIN - 0.0001);
      }
    }
    expect(f.points).toHaveLength(14);
  });

  it('ignore les mentions sans date sans casser la frise', () => {
    const f = frise([jm('2020-03-01'), jm(null), jm('2022-03-01')], 'ubm')!;
    expect(f.points).toHaveLength(2);
  });
});

describe('quiEnParle', () => {
  it('compte chaque voix, une mention à deux voix compte pour les deux', () => {
    const q = quiEnParle([
      jm('2020-01-01', { by: 'Kyan Khojandi & Navo' }),
      jm('2021-01-01', { by: 'Kyan Khojandi' }),
      jm('2022-01-01', { by: null }),
      jm('2023-01-01', { by: 'Antoine Gouy' }),
    ]);
    expect(q.voix.map((v) => [v.nom, v.n])).toEqual([
      ['Kyan Khojandi', 2],
      ['Antoine Gouy', 1],
      ['Navo', 1],
    ]);
    expect(q.voix[0]!.part).toBe(50);
    expect(q.sansAttribution).toBe(1);
    expect(q.total).toBe(4);
    expect(q.aDesVoixCommunes).toBe(true);
  });

  it('une voix répétée dans la même mention ne compte qu’une fois', () => {
    const q = quiEnParle([jm('2020-01-01', { by: 'Navo & Navo' })]);
    expect(q.voix).toEqual([{ nom: 'Navo', n: 1, part: 100 }]);
    expect(q.aDesVoixCommunes).toBe(false);
  });
});

describe('parAnnee', () => {
  it('la plus récente d’abord, l’ordre interne conservé, les sans-date à la fin', () => {
    const a = jm('2026-05-04');
    const b = jm('2026-03-16');
    const c = jm(null);
    const d = jm('2020-03-29');
    const g = parAnnee([a, b, d, c]);
    expect(g.map((x) => x.annee)).toEqual([2026, 2020, null]);
    expect(g[0]!.mentions).toEqual([a, b]);
  });
});
