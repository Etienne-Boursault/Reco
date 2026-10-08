/**
 * Tests de `src/lib/stats/constats.ts` (calculs) et `src/lib/stats/recit.ts`
 * (phrases) — la page /stats en récit, retenue après l'audit d'interface du
 * 2026-10-07. Une phrase écrite au build doit rester vraie : accords,
 * égalités et absences sont couverts ici.
 */
import { describe, expect, it } from 'vitest';

import { calculerConstats, personnes, type CorpusC } from '../../src/lib/stats/constats';
import { duree, rediger } from '../../src/lib/stats/recit';

const d = (iso: string) => new Date(`${iso}T00:00:00Z`);
const ep = (guid: string, date: string, over: Record<string, unknown> = {}) =>
  ({ guid, sourceId: 'ubm', title: `Épisode ${guid}`, date: d(date), season: null, number: null, ...over });
const reco = (id: string, episodeGuid: string, over: Record<string, unknown> = {}) =>
  ({ id, sourceId: 'ubm', episodeGuid, status: 'validated', kind: 'reco', recommendedBy: null, ...over });
const mention = (itemId: string, episodeGuid: string, status: 'validated' | 'discarded' = 'validated') =>
  ({ itemId, status, sourceRef: { sourceId: 'ubm', episodeGuid } });
const item = (id: string, types = ['film'], creator: string | null = null) => ({ id, title: id, types, creator });

function corpus(over: Partial<CorpusC> = {}): CorpusC {
  return {
    sources: [{ id: 'ubm', title: 'Un Bon Moment', hosts: ['Kyan Khojandi', 'Navo'] }],
    episodes: [ep('e1', '2020-02-10'), ep('e2', '2021-05-01'), ep('e3', '2026-08-20')],
    items: [item('Bref', ['serie'], 'Kyan Khojandi'), item('Pulsions', ['spectacle']), item('Seul')],
    mentions: [
      mention('Bref', 'e1'), mention('Bref', 'e2'), mention('Bref', 'e3'),
      mention('Pulsions', 'e1'), mention('Pulsions', 'e2'),
      mention('Seul', 'e3'),
    ],
    recos: [
      reco('r1', 'e1', { recommendedBy: 'Kyan Khojandi' }),
      reco('r2', 'e1', { recommendedBy: 'Kyan Khojandi & Navo' }),
      reco('r3', 'e2', { recommendedBy: 'Albert Dupontel' }),
      reco('r4', 'e2', { recommendedBy: 'Albert Dupontel', kind: 'citation' }),
      reco('r5', 'e2', { recommendedBy: 'Navo & Albert Dupontel' }),
      reco('r6', 'e3'),
      reco('r7', 'e3', { status: 'discarded', recommendedBy: 'Kyan Khojandi' }),
    ],
    ...over,
  };
}

describe('personnes', () => {
  it('sépare &, virgules et « et »', () => {
    expect(personnes('Kyan Khojandi & Navo, Orelsan et Gringe')).toEqual(['Kyan Khojandi', 'Navo', 'Orelsan', 'Gringe']);
    expect(personnes(null)).toEqual([]);
  });
});

describe('calculerConstats', () => {
  const c = calculerConstats(corpus());

  it('compte comme l’accueil : recos publiées non citées, citations à part', () => {
    expect(c.recommandations).toBe(5);
    expect(c.evoquees).toBe(1);
    expect(c.episodes).toBe(3);
    expect(c.oeuvres).toBe(3);
  });

  it('l’œuvre la plus citée l’est en ÉPISODES distincts, avec sa période', () => {
    expect(c.oeuvreLaPlusCitee).toMatchObject({ titre: 'Bref', episodes: 3, createur: 'Kyan Khojandi' });
    expect(c.oeuvreLaPlusCitee!.debut).toEqual(d('2020-02-10'));
    expect(c.oeuvreLaPlusCitee!.fin).toEqual(d('2026-08-20'));
    expect(c.oeuvreLaPlusCitee!.suivante).toEqual({ titre: 'Pulsions', episodes: 2 });
  });

  it('une mention écartée ne compte pas', () => {
    const c2 = calculerConstats(corpus({ mentions: [mention('Seul', 'e1', 'discarded')] }));
    expect(c2.oeuvres).toBe(0);
    expect(c2.oeuvreLaPlusCitee).toBeNull();
    expect(c2.uneSeuleFois).toBeNull();
  });

  it('distingue les œuvres citées une fois', () => {
    expect(c.uneSeuleFois).toEqual({ une: 1, plusieurs: 2, total: 3 });
  });

  it('qui recommande : un nom partagé compte pour chacun, les invités à part', () => {
    expect(c.quiRecommande).toEqual({
      total: 5,
      hotes: [{ nom: 'Kyan Khojandi', n: 2 }, { nom: 'Navo', n: 2 }],
      aPlusieursHotes: 1,
      invites: 1,
      sansAttribution: 1,
    });
  });

  it('l’invité record compte une attribution partagée (« Navo & Albert Dupontel »)', () => {
    expect(c.invitePlusProlixe).toMatchObject({ nom: 'Albert Dupontel', oeuvres: 3, recommandees: 2, egalite: [] });
    expect(c.invitePlusProlixe!.episode.guid).toBe('e2');
  });

  it('les années comptent les épisodes même sans reco', () => {
    expect(c.annees).toEqual([
      { annee: 2020, episodes: 1, recommandations: 2 },
      { annee: 2021, episodes: 1, recommandations: 2 },
      { annee: 2026, episodes: 1, recommandations: 1 },
    ]);
  });

  it('se restreint à une source', () => {
    const autre = calculerConstats(corpus(), 'autre');
    expect(autre.recommandations).toBe(0);
    expect(autre.oeuvreLaPlusCitee).toBeNull();
    expect(autre.quiRecommande).toBeNull();
  });
});

describe('rediger', () => {
  const podcasts = new Map([['ubm', 'Un Bon Moment']]);

  it('écrit un titre et un chapeau accordés', () => {
    const r = rediger(calculerConstats(corpus()), podcasts);
    expect(r.surtitre).toBe('Statistiques · depuis février 2020');
    expect(r.titre).toMatch(/^6 ans et demi de recos, en \d constats$/);
    expect(r.chapeau).toBe('3 épisodes, 5 recommandations et 1 œuvre évoquée : 3 œuvres différentes en tout.');
  });

  it('rédige l’œuvre la plus citée avec sa période et sa suivante', () => {
    const o = rediger(calculerConstats(corpus()), podcasts).constats.find((x) => x.id === 'oeuvre')!;
    expect(o.chiffre).toBe('3');
    expect(o.legende).toBe('épisodes citent Bref');
    expect(o.phrase).toBe('Bref, de Kyan Khojandi, est l’œuvre qui revient le plus. On en parle de février 2020 à août 2026. Pulsions suit avec 2 épisodes.');
  });

  it('dit une égalité comme telle', () => {
    const c = calculerConstats(corpus({ mentions: [mention('Bref', 'e1'), mention('Pulsions', 'e2')] }));
    const o = rediger(c, podcasts).constats.find((x) => x.id === 'oeuvre')!;
    expect(o.legende).toBe('épisode cite Bref');
    expect(o.phrase).toContain('Pulsions fait jeu égal.');
  });

  it('ne garde « recommande large » que si la majorité ne passe qu’une fois', () => {
    const r = rediger(calculerConstats(corpus()), podcasts).constats.find((x) => x.id === 'une-fois')!;
    expect(r.chiffre).toBe('33 %');
    expect(r.phrase).toBe('1 des 3 œuvres n’est citée que dans une seule mention.');
  });

  it('rédige qui recommande, sans attribution comprise', () => {
    const q = rediger(calculerConstats(corpus()), podcasts).constats.find((x) => x.id === 'qui')!;
    expect(q.phrase).toBe('Sur 5 recommandations, Kyan Khojandi en signe 2 et Navo 2, dont 1 à deux. Les invités en signent 1. Il en reste 1 sans attribution.');
    expect(q.graphique.barres.map((b) => b.label)).toEqual(['Kyan Khojandi', 'Navo', 'Invités', 'Sans attribution']);
  });

  it('sans animateur déclaré, le constat « qui » disparaît', () => {
    const c = calculerConstats(corpus({ sources: [{ id: 'ubm', title: 'Un Bon Moment', hosts: [] }] }));
    expect(rediger(c, podcasts).constats.find((x) => x.id === 'qui')).toBeUndefined();
  });

  it('rédige l’invité record sans pronom', () => {
    const p = rediger(calculerConstats(corpus()), podcasts).constats.find((x) => x.id === 'invite')!;
    expect(p.legende).toBe('œuvres citées par Albert Dupontel en un épisode');
    expect(p.phrase).toBe('Dans « Épisode e2 », Albert Dupontel en cite 3, dont 2 recommandées. Aucun autre invité n’en cite autant en un épisode.');
  });

  it('une année de moins de trois épisodes ne fait pas de record', () => {
    expect(rediger(calculerConstats(corpus()), podcasts).constats.find((x) => x.id === 'annees')).toBeUndefined();
  });

  it('l’année la plus riche, et la fourchette des autres', () => {
    const episodes = ['a', 'b', 'c'].flatMap((x) => [ep(`${x}1`, '2024-01-01'), ep(`${x}2`, '2025-01-01')])
      .concat([ep('z1', '2026-01-01'), ep('z2', '2026-02-01'), ep('z3', '2026-03-01'), ep('z4', '2026-04-01')]);
    const recos = [reco('1', 'a2'), reco('2', 'a2'), reco('3', 'b2'), reco('4', 'a1'), reco('5', 'z1')];
    const a = rediger(calculerConstats(corpus({ episodes, recos })), podcasts).constats.find((x) => x.id === 'annees')!;
    expect(a.chiffre).toBe('1,0');
    expect(a.legende).toBe('recommandations par épisode en 2025');
    expect(a.phrase).toBe('Les autres années tournent entre 0,3 et 0,3. 2026 compte le plus d’épisodes : 4.');
    // L'accent va à l'année du constat, pas à la première du graphique.
    expect(a.graphique.barres.filter((b) => b.enAvant).map((b) => b.label)).toEqual(['2025']);
  });
});

describe('duree', () => {
  it('écrit des années, des demi-années et des mois', () => {
    expect(duree(d('2020-02-01'), d('2026-10-01'))).toBe('6 ans et demi');
    expect(duree(d('2025-01-01'), d('2026-03-01'))).toBe('1 an');
    expect(duree(d('2026-01-01'), d('2026-08-01'))).toBe('7 mois');
  });
});
