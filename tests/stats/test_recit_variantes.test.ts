/**
 * Variantes de rédaction de `src/lib/stats/recit.ts` : chaque phrase de la page
 * /stats dans le cas qui la déclenche. Le corpus réel n'en montre qu'une
 * version ; une phrase écrite au build doit pourtant rester vraie quand les
 * chiffres changent — singulier, égalité, absence, période inconnue.
 */
import { describe, expect, it } from 'vitest';

import type { Constats, EpisodeC } from '../../src/lib/stats/constats';
import { duree, rediger } from '../../src/lib/stats/recit';

const d = (iso: string) => new Date(`${iso}T00:00:00Z`);
const PODCASTS = new Map([['ubm', 'Un Bon Moment']]);
const ep = (over: Partial<EpisodeC> = {}): EpisodeC =>
  ({ guid: 'e1', sourceId: 'ubm', title: 'avec Orelsan', date: d('2024-01-01'), season: null, number: null, ...over });

function base(over: Partial<Constats> = {}): Constats {
  return {
    periode: { debut: d('2020-02-10'), fin: d('2026-08-20') },
    episodes: 113,
    recommandations: 1259,
    evoquees: 356,
    oeuvres: 1075,
    oeuvreLaPlusCitee: null,
    uneSeuleFois: null,
    quiRecommande: null,
    invitePlusProlixe: null,
    types: [],
    annees: [],
    ...over,
  };
}
const constat = (c: Constats, id: string) => rediger(c, PODCASTS).constats.find((x) => x.id === id);

describe('rediger — l’œuvre la plus citée', () => {
  const oeuvre = (over: Record<string, unknown> = {}) => base({
    oeuvreLaPlusCitee: {
      titre: 'Bref', createur: null, episodes: 1, debut: d('2024-03-01'), fin: d('2024-03-20'),
      suivante: null, classement: [{ label: 'Bref', valeur: 1 }], ...over,
    } as Constats['oeuvreLaPlusCitee'],
  });

  it('au singulier, sans créateur ni suivante, sur un seul mois', () => {
    const c = constat(oeuvre(), 'oeuvre')!;
    expect(c.legende).toBe('épisode cite Bref');
    expect(c.phrase).toBe('Bref est l’œuvre qui revient le plus. On en parle en mars 2024.');
  });

  it('dit l’égalité avec la suivante', () => {
    const c = constat(oeuvre({ episodes: 3, suivante: { titre: 'Pulsions', episodes: 3 } }), 'oeuvre')!;
    expect(c.phrase).toContain('Pulsions fait jeu égal.');
  });

  it('se tait sur la période quand une date manque', () => {
    const c = constat(oeuvre({ debut: null }), 'oeuvre')!;
    expect(c.phrase).not.toContain('On en parle');
  });
});

describe('rediger — les œuvres citées une seule fois', () => {
  it('au singulier, sans commentaire sous la moitié', () => {
    const c = constat(base({ uneSeuleFois: { une: 1, plusieurs: 3, total: 4 } }), 'une-fois')!;
    expect(c.chiffre).toBe('25 %');
    expect(c.phrase).toBe('1 des 4 œuvres n’est citée que dans une seule mention.');
  });
});

describe('rediger — qui recommande', () => {
  const qui = (over: Record<string, unknown>) => base({
    quiRecommande: { total: 1, hotes: [{ nom: 'Kyan', n: 1 }], aPlusieursHotes: 0, invites: 0, sansAttribution: 0, ...over },
  });

  it('un seul nom, au singulier, sans invité ni anonyme', () => {
    const c = constat(qui({}), 'qui')!;
    expect(c.legende).toBe('recommandation porte le nom de Kyan');
    expect(c.phrase).toBe('Sur 1 recommandation, Kyan en signe 1. Aucune ne vient d’un invité.');
    expect(c.graphique.note).toBeUndefined();
    expect(c.graphique.barres.map((b) => b.label)).toEqual(['Kyan', 'Invités']);
  });

  it('« à plusieurs » au-delà de deux animateurs', () => {
    const c = constat(qui({
      total: 9, hotes: [{ nom: 'A', n: 5 }, { nom: 'B', n: 3 }, { nom: 'C', n: 2 }], aPlusieursHotes: 1,
    }), 'qui')!;
    expect(c.phrase).toContain('A en signe 5, B 3 et C 2, dont 1 à plusieurs.');
    expect(c.graphique.note).toBeDefined();
  });

  it('aucun constat quand l’animateur de tête n’a rien signé', () => {
    expect(constat(qui({ hotes: [{ nom: 'Kyan', n: 0 }] }), 'qui')).toBeUndefined();
  });
});

describe('rediger — l’invité le plus prolixe', () => {
  const invite = (over: Record<string, unknown>) => base({
    invitePlusProlixe: {
      nom: 'Orelsan', oeuvres: 4, recommandees: 4, episode: ep(), egalite: ['Gringe'],
      plusRiches: [{ episode: ep(), n: 4 }, { episode: ep({ guid: 'e2', season: 5, number: 7, title: 'avec Gringe' }), n: 3 }],
      ...over,
    },
  });

  it('« toutes recommandées », une égalité, un épisode sans numéro', () => {
    const c = constat(invite({}), 'invite')!;
    expect(c.phrase).toBe('Dans « avec Orelsan », Orelsan en cite 4, toutes recommandées. Gringe en cite autant.');
    expect(c.graphique.barres.map((b) => b.label)).toEqual(['avec Orelsan', 'S5·E7 · avec Gringe']);
  });

  it('aucune recommandée : rien n’est ajouté', () => {
    const c = constat(invite({ recommandees: 0, egalite: [], episode: ep({ season: 5, number: 7 }) }), 'invite')!;
    expect(c.phrase).toBe('Dans « avec Orelsan » (S5·E7), Orelsan en cite 4. Aucun autre invité n’en cite autant en un épisode.');
  });
});

describe('rediger — les types', () => {
  it('un type seul, inconnu du libellé : son nom brut, sans suite', () => {
    const c = constat(base({ types: [{ type: 'zarbi', n: 2 }] }), 'types')!;
    expect(c.legende).toBe('zarbi, en tête des types');
    expect(c.phrase).toBe('Sur 2 œuvres, chacune comptée pour son type principal.');
  });

  it('dit l’égalité des deux premiers', () => {
    const c = constat(base({ types: [{ type: 'film', n: 5 }, { type: 'serie', n: 5 }] }), 'types')!;
    expect(c.legende).toContain('à égalité avec les');
  });
});

describe('rediger — les années', () => {
  it('pas de constat sans année d’au moins trois épisodes', () => {
    expect(constat(base({ annees: [{ annee: 2024, episodes: 2, recommandations: 9 }] }), 'annees')).toBeUndefined();
  });

  it('une seule année retenue : la phrase de repli, et un tiret pour l’année vide', () => {
    const c = constat(base({ annees: [
      { annee: 2024, episodes: 4, recommandations: 20 },
      { annee: 2025, episodes: 0, recommandations: 0 },
    ] }), 'annees')!;
    expect(c.phrase).toBe('2024 est l’année la plus riche.');
    expect(c.graphique.barres.find((b) => b.label === '2025')!.affiche).toBe('—');
  });

  it('une autre année, et l’année au plus d’épisodes', () => {
    const c = constat(base({ annees: [
      { annee: 2023, episodes: 10, recommandations: 30 },
      { annee: 2024, episodes: 4, recommandations: 20 },
    ] }), 'annees')!;
    expect(c.phrase).toBe('L’autre année en compte 3,0. 2023 compte le plus d’épisodes : 10.');
  });
});

describe('rediger — en-tête', () => {
  it('sans période : pas de surtitre, un titre sans durée', () => {
    const r = rediger(base({ periode: null, types: [{ type: 'film', n: 1 }] }), PODCASTS);
    expect(r.surtitre).toBeNull();
    expect(r.titre).toBe('Les recos, en 1 constat');
  });
});

describe('duree', () => {
  it('en mois sous un an, « et demi » à partir de six mois', () => {
    expect(duree(d('2024-01-01'), d('2024-01-20'))).toBe('1 mois');
    expect(duree(d('2024-01-01'), d('2024-05-01'))).toBe('4 mois');
    expect(duree(d('2020-01-01'), d('2026-07-01'))).toBe('6 ans et demi');
    expect(duree(d('2025-01-01'), d('2026-02-01'))).toBe('1 an');
  });
});
