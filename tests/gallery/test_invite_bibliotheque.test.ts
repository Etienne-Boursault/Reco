/**
 * Tests de `src/lib/gallery/invite.ts` — la page invité « Bibliothèque ».
 * Les cas reprennent le corpus réel (Florent Bernard, relevé le 2026-10-07).
 */
import { describe, expect, it } from 'vitest';

import {
  bibliothequeDeLInvite,
  initiales,
  passagesDeLInvite,
  prenom,
  type EpisodeInvite,
  type MentionInvite,
  type OeuvreInvite,
} from '../../src/lib/gallery/invite';

const FB = 'Florent Bernard';
const ep = (guid: string, date: string, over: Partial<EpisodeInvite> = {}): EpisodeInvite => ({
  guid,
  title: guid,
  date: new Date(date),
  ...over,
});
const oeuvre = (id: string, types: string[], creator?: string): OeuvreInvite => ({
  id,
  title: id,
  types,
  creator,
});
const mention = (itemId: string, guid: string, over: Partial<MentionInvite> = {}): MentionInvite => ({
  itemId,
  recommendedBy: FB,
  status: 'validated',
  sourceRef: { episodeGuid: guid },
  ...over,
});

const EPISODES = [ep('e3', '2020-02-17'), ep('e1', '2020-02-01'), ep('s5e1', '2025-10-01', { guests: [FB] })];
const OEUVRES = [
  oeuvre('Pitch', ['serie'], 'Baptiste Lecaplain, Florent Bernard, Xavier Maingon'),
  oeuvre('Pulsions', ['spectacle', 'video'], 'Kyan Khojandi, Navo'),
  oeuvre('Souchon', ['album'], 'Alain Souchon'),
  oeuvre('Burning Love', ['serie'], 'Ben Stiller'),
];

describe('bibliothequeDeLInvite', () => {
  const b = bibliothequeDeLInvite(FB, OEUVRES, [
    mention('Pitch', 'e3', { kind: 'reco' }),
    mention('Pulsions', 's5e1', { kind: 'reco' }),
    mention('Souchon', 'e1', { kind: 'reco' }),
    mention('Burning Love', 'e3', { kind: 'citation' }),
  ], EPISODES);

  it('« ses œuvres » = celles dont la personne est créatrice', () => {
    expect(b.sesOeuvres.map((l) => l.oeuvre.id)).toEqual(['Pitch']);
  });

  it('Pulsions, vanté par un invité, est une recommandation, pas son œuvre', () => {
    const recos = b.recommandations.flatMap((g) => g.lignes.map((l) => l.oeuvre.id));
    expect(recos).toContain('Pulsions');
    expect(b.nbRecommandations).toBe(2);
  });

  it('groupe les recommandations par premier type de l’œuvre', () => {
    expect(b.recommandations.map((g) => g.type).sort()).toEqual(['album', 'spectacle']);
  });

  it('les œuvres seulement évoquées sont à part', () => {
    expect(b.evoquees.map((l) => l.oeuvre.id)).toEqual(['Burning Love']);
  });

  it('les passages vont du plus ancien au plus récent, invité de l’épisode compris', () => {
    expect(b.passages.map((e) => e.guid)).toEqual(['e1', 'e3', 's5e1']);
  });
});

describe('règle des recos collectives (inchangée)', () => {
  it('« A & B » ne compte ni pour A ni pour B', () => {
    const b = bibliothequeDeLInvite(FB, OEUVRES, [
      mention('Souchon', 'e1', { recommendedBy: `Kyan Khojandi & ${FB}` }),
    ], EPISODES);
    expect(b.nbRecommandations).toBe(0);
  });

  it('une mention écartée ne compte pas', () => {
    const b = bibliothequeDeLInvite(FB, OEUVRES, [mention('Souchon', 'e1', { status: 'discarded' })], []);
    expect(b.nbRecommandations).toBe(0);
  });
});

describe('passagesDeLInvite', () => {
  it('ignore la casse du nom', () => {
    expect(passagesDeLInvite('florent bernard', EPISODES, []).map((e) => e.guid)).toEqual(['s5e1']);
  });
});

describe('initiales et prénom', () => {
  it('deux lettres au plus', () => {
    expect(initiales('Florent Bernard')).toBe('FB');
    expect(initiales('Jean-Pierre Bacri')).toBe('JP');
    expect(initiales('Orelsan')).toBe('O');
  });

  it('le prénom, ou le nom entier', () => {
    expect(prenom('Florent Bernard')).toBe('Florent');
    expect(prenom('Orelsan')).toBe('Orelsan');
  });

  it('une page de groupe garde le nom entier', () => {
    expect(prenom('Kyan Khojandi & Florent Bernard')).toBe('Kyan Khojandi & Florent Bernard');
  });
});
