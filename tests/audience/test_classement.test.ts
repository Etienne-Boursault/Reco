/**
 * Tests de `src/lib/audience/classement.ts` : le tri en trois colonnes
 * (AU-1 A, 27/11). Une case de la table R-6, un test.
 */
import { describe, expect, it } from 'vitest';

import {
  cheminNormalise,
  classer,
  compterColonnes,
  dateDeBascule,
  estSignal,
  joursEnPanne,
  sommerColonnes,
  type Colonnes,
} from '../../src/lib/audience/classement';

function visite(over: Record<string, unknown> = {}) {
  return {
    ts: '2026-11-27T10:00:00.000Z',
    chemin: '/a-propos',
    statut: 200,
    robot: false,
    langue: 'fr',
    hebergeur: false,
    visiteur: 'aaaaaaaaaaaa',
    ...over,
  } as Parameters<typeof classer>[0][number];
}

function signal(over: Record<string, unknown> = {}) {
  return {
    ts: '2026-11-27T10:00:00.000Z',
    nature: 'signal' as const,
    chemin: '/a-propos',
    hebergeur: false,
    visiteur: 'aaaaaaaaaaaa',
    ...over,
  };
}

const un = (v: ReturnType<typeof visite>, s: ReturnType<typeof signal>[] = []) =>
  classer([v], s)[0];

describe('la table du tri (R-6), lue dans l’ordre', () => {
  it('1. un robot déclaré est un robot, même avec un signal', () => {
    expect(un(visite({ robot: true }), [signal()])).toBe('robot');
  });

  it('2. sans langue : robot, même avec un signal', () => {
    expect(un(visite({ langue: null }), [signal()])).toBe('robot');
  });

  it('3. un signal valide d’un particulier : confirmé', () => {
    expect(un(visite(), [signal()])).toBe('confirme');
  });

  it('4a. un hébergeur sans signal : robot', () => {
    expect(un(visite({ hebergeur: true }))).toBe('robot');
  });

  it('4b. un hébergeur avec signal reste incertain, jamais confirmé', () => {
    expect(un(visite({ hebergeur: true }), [signal({ hebergeur: true })])).toBe('incertain');
  });

  it('5. un particulier sans signal : incertain', () => {
    expect(un(visite())).toBe('incertain');
  });
});

describe('le signal ne confirme qu’avec sa page (R-5)', () => {
  it('un signal orphelin (autre page) ne confirme rien', () => {
    expect(un(visite(), [signal({ chemin: '/autre' })])).toBe('incertain');
  });

  it('un signal d’un autre visiteur ne confirme rien', () => {
    expect(un(visite(), [signal({ visiteur: 'bbbbbbbbbbbb' })])).toBe('incertain');
  });

  it('la barre finale ne distingue pas deux pages', () => {
    expect(un(visite(), [signal({ chemin: '/a-propos/' })])).toBe('confirme');
  });

  it('un signal une heure après ou avant la page confirme encore', () => {
    expect(un(visite(), [signal({ ts: '2026-11-27T11:00:00.000Z' })])).toBe('confirme');
    expect(un(visite(), [signal({ ts: '2026-11-27T09:00:00.000Z' })])).toBe('confirme');
  });

  it('un signal hors délai (deux heures) ne confirme rien', () => {
    expect(un(visite(), [signal({ ts: '2026-11-27T12:00:00.000Z' })])).toBe('incertain');
  });

  it('un visiteur null n’est jamais confirmé, même face à un signal null', () => {
    expect(un(visite({ visiteur: null }), [signal({ visiteur: null })])).toBe('incertain');
  });

  it('un visiteur null chez un hébergeur reste un robot', () => {
    expect(un(visite({ visiteur: null, hebergeur: true }))).toBe('robot');
  });

  it('le signal confirme les autres pages du même visiteur-jour', () => {
    const [a, b] = classer([visite(), visite({ chemin: '/autre', ts: '2026-11-27T14:00:00.000Z' })], [
      signal(),
    ]);
    expect([a, b]).toEqual(['confirme', 'confirme']);
  });

  it('le passage de minuit UTC recoud rien : l’empreinte change, le signal reste orphelin', () => {
    // Page à 23 h 59 (heure ronde 23 h), signal à 00 h 01 le lendemain : sel
    // différent, donc empreinte différente.
    const soir = visite({ ts: '2026-11-27T23:00:00.000Z', visiteur: 'aaaaaaaaaaaa' });
    const nuit = signal({ ts: '2026-11-28T00:00:00.000Z', visiteur: 'cccccccccccc' });
    expect(un(soir, [nuit])).toBe('incertain');
    expect(classer([], [nuit])).toEqual([]);
  });
});

describe('les lignes d’avant la tranche A (sans champ hebergeur) : ancien tri', () => {
  it('un humain d’avant reste compté, jamais confirmé ni hébergeur', () => {
    const ancienne = visite();
    delete (ancienne as { hebergeur?: boolean }).hebergeur;
    expect(un(ancienne, [signal()])).toBe('incertain');
  });

  it('un robot d’avant reste un robot', () => {
    const ancienne = visite({ langue: null });
    delete (ancienne as { hebergeur?: boolean }).hebergeur;
    expect(un(ancienne)).toBe('robot');
  });
});

describe('les trois oui/non du signal ne changent pas le tri (AU-2 B, 2026-11-27)', () => {
  const combinaisons = [true, false, null].flatMap((revenant) =>
    [true, false, null].flatMap((aVuEpisode) =>
      [true, false, null].map((aVuFiche) => ({ revenant, aVuEpisode, aVuFiche })),
    ),
  );

  it.each([
    ['particulier avec signal', visite(), false, 'confirme'],
    ['particulier sans signal', visite({ visiteur: 'bbbbbbbbbbbb' }), false, 'incertain'],
    ['hébergeur avec signal', visite({ hebergeur: true }), true, 'incertain'],
    ['robot déclaré avec signal', visite({ robot: true }), false, 'robot'],
  ])('%s : même classe, quelles que soient les 27 combinaisons', (_nom, v, hebergeur, attendu) => {
    for (const trois of combinaisons) {
      expect(classer([v], [signal({ ...trois, hebergeur })])).toEqual([attendu]);
    }
  });
});

describe('estSignal', () => {
  it('ne reconnaît que nature "signal"', () => {
    expect(estSignal({ nature: 'signal' })).toBe(true);
    expect(estSignal({})).toBe(false);
    expect(estSignal({ nature: 'autre' })).toBe(false);
  });
});

describe('cheminNormalise', () => {
  it('garde la racine et retire les barres finales', () => {
    expect(cheminNormalise('/')).toBe('/');
    expect(cheminNormalise('/a//')).toBe('/a');
    expect(cheminNormalise('//')).toBe('/');
  });
});

describe('compterColonnes', () => {
  it('compte visites et visiteurs-jours, la meilleure colonne emportant le visiteur', () => {
    const vs = [
      visite({ visiteur: 'aaaaaaaaaaaa' }),
      visite({ visiteur: 'aaaaaaaaaaaa', robot: true }),
      visite({ visiteur: 'bbbbbbbbbbbb' }),
      visite({ visiteur: 'dddddddddddd', hebergeur: true }),
      visite({ visiteur: null }),
    ];
    const cls = classer(vs, [signal()]);
    expect(cls).toEqual(['confirme', 'robot', 'incertain', 'robot', 'incertain']);
    expect(compterColonnes(vs, cls)).toEqual({
      confirmes: { visiteursJours: 1, visites: 1 },
      incertains: { visiteursJours: 1, visites: 2 },
      robots: { visiteursJours: 1, visites: 2 },
    });
  });

  it('rend des zéros sans visite', () => {
    const zero = { visiteursJours: 0, visites: 0 };
    expect(compterColonnes([], [])).toEqual({ confirmes: zero, incertains: zero, robots: zero });
  });
});

describe('sommerColonnes', () => {
  it('additionne jour par jour, et rend null sans colonnes', () => {
    const c = (n: number): Colonnes => ({
      confirmes: { visiteursJours: n, visites: n },
      incertains: { visiteursJours: 2 * n, visites: 2 * n },
      robots: { visiteursJours: 3 * n, visites: 3 * n },
    });
    expect(sommerColonnes([c(1), null, c(2)])).toEqual(c(3));
    expect(sommerColonnes([null])).toBeNull();
    expect(sommerColonnes([])).toBeNull();
  });
});

describe('dateDeBascule (R-7)', () => {
  it('est nulle tant qu’aucun signal n’existe', () => {
    expect(dateDeBascule([])).toBeNull();
    expect(dateDeBascule([{ jour: '2026-11-26', signaux: 0 }])).toBeNull();
  });

  it('écarte le premier jour de signaux, probablement incomplet', () => {
    const j = [
      { jour: '2026-11-26', signaux: 0 },
      { jour: '2026-11-27', signaux: 4 },
      { jour: '2026-11-28', signaux: 9 },
    ];
    expect(dateDeBascule(j)).toBe('2026-11-28');
    expect(dateDeBascule(j.slice(0, 2))).toBeNull();
  });

  it('tient le premier jour lu pour complet quand il porte déjà des signaux', () => {
    expect(dateDeBascule([{ jour: '2026-11-27', signaux: 4 }])).toBe('2026-11-27');
  });
});

describe('joursEnPanne (R-7)', () => {
  const col = (n: number): Colonnes => ({
    confirmes: { visiteursJours: 0, visites: 0 },
    incertains: { visiteursJours: n, visites: n },
    robots: { visiteursJours: 0, visites: 0 },
  });
  const aujourdhui = new Date('2026-11-30T12:00:00Z');

  it('signale un jour complet récent avec des visites et aucun signal', () => {
    const j = [{ jour: '2026-11-29', signaux: 0, colonnes: col(8) }];
    expect(joursEnPanne(j, '2026-11-27', aujourdhui)).toEqual(['2026-11-29']);
  });

  it('ignore aujourd’hui (incomplet), les jours anciens, ceux avant la bascule, les petits jours et les jours à signaux', () => {
    const j = [
      { jour: '2026-11-30', signaux: 0, colonnes: col(8) },
      { jour: '2026-11-27', signaux: 0, colonnes: col(8) },
      { jour: '2026-11-29', signaux: 0, colonnes: col(2) },
      { jour: '2026-11-28', signaux: 3, colonnes: col(8) },
    ];
    expect(joursEnPanne(j, '2026-11-28', aujourdhui)).toEqual([]);
    expect(joursEnPanne(j, '2026-12-01', aujourdhui)).toEqual([]);
  });

  it('ignore un jour sans colonnes (ancien tri) et une bascule nulle', () => {
    expect(joursEnPanne([{ jour: '2026-11-29', signaux: 0, colonnes: null }], '2026-11-27', aujourdhui)).toEqual([]);
    expect(joursEnPanne([{ jour: '2026-11-29', signaux: 0, colonnes: col(9) }], null, aujourdhui)).toEqual([]);
  });
});
