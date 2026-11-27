/**
 * Tests de `src/lib/audience/parcours.ts` : les revenants et le chemin
 * épisode → fiche → clic, en parts agrégées (AU-2 B, 27/11 ; R-1, R-13).
 */
import { describe, expect, it } from 'vitest';

import type { LigneVisite, Signal } from '../../src/lib/audience/classement';
import {
  brutVide,
  compterJour,
  parts,
  SEUIL_PARCOURS,
  sommer,
  type Brut,
} from '../../src/lib/audience/parcours';

const visiteur = (i: number) => `v${String(i).padStart(11, '0')}`;

function visite(i: number): LigneVisite {
  return { ts: '2026-11-27T10:00:00.000Z', chemin: '/a', robot: false, langue: 'fr', hebergeur: false, visiteur: visiteur(i) };
}

function signal(i: number, over: Partial<Signal> = {}): Signal {
  return { ts: '2026-11-27T10:00:00.000Z', nature: 'signal', chemin: '/a', hebergeur: false, visiteur: visiteur(i), ...over };
}

/** `n` visiteurs-jours confirmés, chacun avec un signal fabriqué par `fab(i)`. */
function jour(n: number, fab: (i: number) => Partial<Signal>, classe: 'confirme' | 'incertain' = 'confirme') {
  const visites = Array.from({ length: n }, (_, i) => visite(i));
  const signaux = Array.from({ length: n }, (_, i) => signal(i, fab(i)));
  return compterJour(visites, visites.map(() => classe), signaux, []);
}

describe('revenants', () => {
  it('compte oui et non parmi les visiteurs confirmés', () => {
    const b = jour(25, (i) => ({ revenant: i < 10 }));
    expect(b.revenants).toEqual({ oui: 10, non: 15 });
    expect(parts(b).revenants).toEqual({ oui: 10, total: 25, pct: 40 });
  });

  it('les inconnus (null, absent) ne sont ni au numérateur ni au dénominateur', () => {
    const b = jour(30, (i) => (i < 10 ? { revenant: true } : i < 20 ? { revenant: false } : i < 25 ? { revenant: null } : {}));
    expect(b.revenants).toEqual({ oui: 10, non: 10 });
    expect(parts(b).revenants?.total).toBe(20);
  });

  it('exclut les visiteurs non confirmés (incertains)', () => {
    const b = jour(25, () => ({ revenant: true }), 'incertain');
    expect(b.revenants).toEqual({ oui: 0, non: 0 });
  });

  it('un signal sans visiteur, ou d’un visiteur sans visite confirmée, ne compte pas', () => {
    const visites = [visite(0)];
    const b = compterJour(
      visites,
      ['confirme'],
      [signal(0, { revenant: true }), signal(1, { revenant: true }), signal(0, { visiteur: null, revenant: false })],
      [],
    );
    expect(b.revenants).toEqual({ oui: 1, non: 0 });
  });

  it('un visiteur-jour à plusieurs signaux compte une fois, avec le « ou »', () => {
    const visites = [visite(0), visite(1), visite(2)];
    const b = compterJour(
      visites,
      ['confirme', 'confirme', 'confirme'],
      [
        signal(0, { revenant: false }), signal(0, { revenant: true }),
        signal(1, { revenant: false }), signal(1, { revenant: null }),
        signal(2, { revenant: null }), signal(2),
      ],
      [],
    );
    expect(b.revenants).toEqual({ oui: 1, non: 1 });
  });

  it('sans classes (avant la bascule), aucun signal n’est compté', () => {
    const b = compterJour([visite(0)], null, [signal(0, { revenant: true })], []);
    expect(b.revenants).toEqual({ oui: 0, non: 0 });
  });
});

describe('seuil de 10', () => {
  const part = (oui: number, non: number) => parts({ ...brutVide(), revenants: { oui, non } }).revenants;

  it('le seuil vaut 10', () => expect(SEUIL_PARCOURS).toBe(10));
  it('dénominateur 9 : trop peu de données', () => expect(part(5, 4)).toBeNull());
  it('dénominateur 10 mais cases à 5 : trop peu de données', () => expect(part(5, 5)).toBeNull());
  it('une case à 9 : trop peu de données, dans les deux sens', () => {
    expect(part(9, 50)).toBeNull();
    expect(part(50, 9)).toBeNull();
  });
  it('les deux cases à 10 : affichée', () => expect(part(10, 10)).toEqual({ oui: 10, total: 20, pct: 50 }));
  it('arrondit le pourcentage au dixième', () => expect(part(10, 20)?.pct).toBe(33.3));
});

describe('le chemin épisode → fiche → clic', () => {
  it('parmi ceux qui ont vu un épisode, la part qui a vu une fiche', () => {
    // 0-11 : épisode vu ; 0-4 aussi fiche ; 12-14 : fiche sans épisode (hors chemin) ; 15-16 : épisode inconnu.
    const b = jour(17, (i) =>
      i < 5 ? { aVuEpisode: true, aVuFiche: true }
        : i < 12 ? { aVuEpisode: true, aVuFiche: i === 5 ? null : false }
          : i < 15 ? { aVuEpisode: false, aVuFiche: true }
            : { aVuEpisode: null, aVuFiche: true },
    );
    // Épisode vu : 12 ; fiche vue : 5 ; non : 6 ; une fiche inconnue.
    expect(b.fiche).toEqual({ oui: 5, non: 6 });
  });

  it('assez de monde : la part est rendue', () => {
    const b = jour(30, (i) => ({ aVuEpisode: true, aVuFiche: i < 12 }));
    expect(parts(b).vuFiche).toEqual({ oui: 12, total: 30, pct: 40 });
  });

  it('le « ou » du jour : un épisode vu à un moment de la journée compte', () => {
    const visites = [visite(0)];
    const b = compterJour(
      visites,
      ['confirme'],
      [signal(0, { aVuEpisode: false, aVuFiche: false }), signal(0, { aVuEpisode: true, aVuFiche: false }), signal(0, { aVuEpisode: true, aVuFiche: true })],
      [],
    );
    expect(b.fiche).toEqual({ oui: 1, non: 0 });
  });

  it('les clics : la part portant aVuEpisode et celle portant aVuFiche, inconnus à part', () => {
    const clics = [
      ...Array.from({ length: 12 }, () => ({ aVuEpisode: true, aVuFiche: true })),
      ...Array.from({ length: 11 }, () => ({ aVuEpisode: true, aVuFiche: false })),
      ...Array.from({ length: 10 }, () => ({ aVuEpisode: false, aVuFiche: false })),
      { aVuEpisode: null, aVuFiche: null },
    ];
    const b = compterJour([], null, [], clics);
    expect(b.clicEpisode).toEqual({ oui: 23, non: 10 });
    expect(b.clicFiche).toEqual({ oui: 12, non: 21 });
    const p = parts(b);
    expect(p.clicsEpisode).toEqual({ oui: 23, total: 33, pct: 69.7 });
    expect(p.clicsFiche).toEqual({ oui: 12, total: 33, pct: 36.4 });
  });

  it('les clics d’avant D1, sans les champs, sont inconnus', () => {
    const b = compterJour([], null, [], [{}, {}, { aVuEpisode: undefined }]);
    expect(b.clicEpisode).toEqual({ oui: 0, non: 0 });
    expect(b.clicFiche).toEqual({ oui: 0, non: 0 });
  });
});

describe('sommer', () => {
  it('additionne les comptes de plusieurs jours, sans toucher aux entrées', () => {
    const a: Brut = { ...brutVide(), revenants: { oui: 3, non: 4 } };
    const b: Brut = { ...brutVide(), revenants: { oui: 5, non: 1 }, clicFiche: { oui: 2, non: 2 } };
    const s = sommer([a, b]);
    expect(s.revenants).toEqual({ oui: 8, non: 5 });
    expect(s.clicFiche).toEqual({ oui: 2, non: 2 });
    expect(a.revenants).toEqual({ oui: 3, non: 4 });
    expect(sommer([])).toEqual(brutVide());
  });

  it('parts d’un compte vide : tout est « trop peu de données »', () => {
    expect(parts(brutVide())).toEqual({ revenants: null, vuFiche: null, clicsEpisode: null, clicsFiche: null });
  });
});
