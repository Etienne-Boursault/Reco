/**
 * Tests de `src/utils/verbeMention.ts` — « Présentée par » n'est juste que
 * pour l'auteur de l'œuvre (cas réels du corpus, relevés le 2026-10-07).
 */
import { describe, expect, it } from 'vitest';

import { parleDeSonOeuvre, verbeMention } from '../../src/utils/verbeMention';

const PULSIONS = 'Kyan Khojandi, Navo';

describe('verbeMention', () => {
  it('l’auteur qui parle de son œuvre la présente (ubm-1477, Kyan et Pulsions)', () => {
    expect(verbeMention({ guestWork: true, recommendedBy: 'Kyan Khojandi', creator: PULSIONS }))
      .toBe('Présentée par');
  });

  it('un invité qui vante l’œuvre d’un host la recommande (ubm-2313, Kheiron et Pulsions)', () => {
    expect(verbeMention({ guestWork: true, recommendedBy: 'Kheiron', creator: PULSIONS }))
      .toBe('Reco de');
  });

  it('un host qui annonce le spectacle d’un invité le recommande (Irréalisable)', () => {
    expect(verbeMention({ guestWork: true, recommendedBy: 'Kyan Khojandi', creator: 'Babor Lelefan' }))
      .toBe('Reco de');
  });

  it('une citation reste « Évoquée par », même œuvre d’invité', () => {
    expect(verbeMention({ kind: 'citation', guestWork: true, recommendedBy: 'Yassir', creator: PULSIONS }))
      .toBe('Évoquée par');
  });

  it('sans drapeau guestWork, toujours « Reco de »', () => {
    expect(verbeMention({ recommendedBy: 'Kyan Khojandi', creator: PULSIONS })).toBe('Reco de');
  });

  it('sans créateur connu, on ne peut rien affirmer : « Reco de »', () => {
    expect(verbeMention({ guestWork: true, recommendedBy: 'Florent Bernard', creator: null }))
      .toBe('Reco de');
  });
});

describe('parleDeSonOeuvre', () => {
  it('reconnaît un auteur parmi plusieurs personnes qui en parlent', () => {
    expect(parleDeSonOeuvre('Kyan Khojandi & Navo', PULSIONS)).toBe(true);
  });

  it('ignore la casse et les accents', () => {
    expect(parleDeSonOeuvre('adrien menielle', 'Adrien Ménielle')).toBe(true);
  });

  it('accepte « et » comme séparateur', () => {
    expect(parleDeSonOeuvre('Florent Bernard', 'Baptiste Lecaplain, Florent Bernard et Xavier Maingon'))
      .toBe(true);
  });

  it('un nom d’un seul mot vaut pour le prénom d’un créateur (Babor, Irregardable)', () => {
    expect(parleDeSonOeuvre('Babor', 'Babor Lelefan')).toBe(true);
    expect(parleDeSonOeuvre('Babor', 'Babor Lelefan, Camille Fievez, Etienne Lautrette')).toBe(true);
  });

  it('un nom complet ne vaut pas pour un autre nom complet au même prénom', () => {
    expect(parleDeSonOeuvre('Paul Mirabel', 'Paul Thomas Anderson')).toBe(false);
  });

  it('un nom qui en CONTIENT un autre ne suffit pas', () => {
    expect(parleDeSonOeuvre('Navo', 'Navoleon')).toBe(false);
  });
});
