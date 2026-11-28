/**
 * Tests de `src/lib/bord/resume.ts` — ce que `/api/bord` rend au tableau de
 * bord de venus (tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026,
 * l'audience au centre).
 *
 * Le module est pur : il reçoit deux lectures de `lireAudience` et les
 * signalements, et choisit ce qui part. Deux propriétés comptent plus que les
 * autres : il ne recompte rien (les chiffres sont ceux de l'agrégat, tels
 * quels), et un signalement ne sort jamais avec le nom, l'adresse ou le texte
 * de la personne qui l'a envoyé (F15).
 */
import { describe, expect, it } from 'vitest';

import { resumerBord } from '../../src/lib/bord/resume';
import type { Agregat, Jour } from '../../src/lib/audience/agregat';
import type { Colonnes } from '../../src/lib/audience/classement';
import type { LectureAudience } from '../../src/lib/audience/vue';
import type { Report } from '../../src/lib/reports/types';

const COLONNES: Colonnes = {
  confirmes: { visiteursJours: 4, visites: 9 },
  incertains: { visiteursJours: 2, visites: 3 },
  robots: { visiteursJours: 5, visites: 40 },
};

function jour(over: Partial<Jour> = {}): Jour {
  return {
    jour: '2026-11-26', pages: 12, visiteurs: 6, robots: 40, prechargements: 1,
    clics: 2, signaux: 7, colonnes: COLONNES, ...over,
  };
}

const compte = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ cle: `/page-${i}`, n: 100 - i }));

function agregat(over: Partial<Agregat> = {}): Agregat {
  return {
    du: '2026-11-22', au: '2026-11-28', jours: [jour()], pagesVues: 12, visiteurs: 6,
    visitesRobots: 40, prechargements: 1, clics: 2, clicsPour100Visiteurs: 33.3,
    clicsHorsPeriode: 0, topPages: compte(7),
    provenances: compte(6).map((c) => ({ ...c, cle: `site-${c.n}.test` })),
    appareils: [{ cle: 'mobile', n: 3 }], langues: [{ cle: 'fr', n: 3 }],
    paysConnus: [{ cle: 'FR', n: 3 }], paysIndisponible: false,
    erreurs404: [{ cle: '/vieux', n: 1 }], sondes: 4, plateformes: [{ cle: 'tmdb', n: 2 }],
    dureeMedianeMs: 12, bascule: '2026-11-25', colonnes: COLONNES,
    panneSignal: ['2026-11-27'],
    parcours: { revenants: null, vuFiche: null, clicsEpisode: null, clicsFiche: null },
    ...over,
  };
}

function lecture(donnees: Agregat | null, erreur: string | null = null): LectureAudience {
  return { sources: ['_site', 'un-bon-moment'], libelle: 'tout le site · _site, un-bon-moment', donnees, erreur };
}

function signalement(over: Partial<Report> = {}): Report {
  return {
    id: 'rep-1', sourceId: 'un-bon-moment', recoId: 'ubm-1', category: 'error',
    details: 'Texte libre écrit par la personne',
    submitter: { name: 'Prénom Nom', email: 'personne@exemple.test', wantCredit: true },
    submittedAt: '2026-11-27T08:00:00.000Z', status: 'pending',
    resolvedAt: null, resolvedBy: null, notes: 'note de l’éditeur', ...over,
  };
}

const MAINTENANT = new Date('2026-11-28T09:30:00.000Z');

function resumer(over: Partial<Parameters<typeof resumerBord>[0]> = {}) {
  return resumerBord({
    sept: lecture(agregat()),
    trente: lecture(agregat({ visiteurs: 30, du: '2026-10-30' })),
    signalements: [],
    maintenant: MAINTENANT,
    ...over,
  });
}

describe('resumerBord : les fenêtres de 7 et 30 jours', () => {
  it('reprend les chiffres de l’agrégat sans les recompter', () => {
    const r = resumer();

    expect(r.sept).toEqual({
      du: '2026-11-22', au: '2026-11-28', tri: 'trois-colonnes', bascule: '2026-11-25',
      panneSignal: ['2026-11-27'], colonnes: COLONNES, pagesVues: 12, visiteurs: 6,
      visitesRobots: 40, clics: 2, clicsPour100Visiteurs: 33.3,
      pages: compte(5),
      provenances: compte(5).map((c) => ({ ...c, cle: `site-${c.n}.test` })),
    });
    expect(r.trente?.visiteurs).toBe(30);
    expect(r.trente?.du).toBe('2026-10-30');
  });

  it('dit « ancien tri » avant la bascule, sans colonnes', () => {
    const avant = agregat({
      bascule: null, colonnes: null, panneSignal: [],
      jours: [jour({ colonnes: null, signaux: 0, visiteurs: 3, robots: 8 })],
    });
    const r = resumer({ sept: lecture(avant), trente: lecture(avant) });

    expect(r.sept?.tri).toBe('ancien');
    expect(r.sept?.colonnes).toBeNull();
    expect(r.sept?.bascule).toBeNull();
    expect(r.trente?.tri).toBe('ancien');
    expect(r.jours).toEqual([{ jour: '2026-11-26', tri: 'ancien', visiteurs: 3, robots: 8, colonnes: null }]);
  });

  it('rend une fenêtre absente et l’erreur quand la lecture a échoué', () => {
    const r = resumer({ sept: lecture(null, 'lecture impossible'), trente: lecture(null, 'autre') });

    expect(r.sept).toBeNull();
    expect(r.trente).toBeNull();
    expect(r.jours).toEqual([]);
    expect(r.erreur).toBe('lecture impossible');
  });

  it('rend l’erreur de 30 jours quand seule celle-ci a échoué', () => {
    const r = resumer({ trente: lecture(null, 'trente en échec') });

    expect(r.sept).not.toBeNull();
    expect(r.erreur).toBe('trente en échec');
  });

  it('donne le périmètre lu et l’heure de génération', () => {
    const r = resumer();

    expect(r.perimetre).toBe('tout le site · _site, un-bon-moment');
    expect(r.genere).toBe('2026-11-28T09:30:00.000Z');
    expect(r.erreur).toBeNull();
  });
});

describe('resumerBord : les jours un par un', () => {
  it('reprend les jours de la fenêtre de 7 jours, chacun avec son tri', () => {
    const jours = [
      jour({ jour: '2026-11-24', colonnes: null, visiteurs: 2, robots: 5 }),
      jour({ jour: '2026-11-25' }),
    ];
    const r = resumer({ sept: lecture(agregat({ jours })) });

    expect(r.jours).toEqual([
      { jour: '2026-11-24', tri: 'ancien', visiteurs: 2, robots: 5, colonnes: null },
      { jour: '2026-11-25', tri: 'trois-colonnes', visiteurs: 6, robots: 40, colonnes: COLONNES },
    ]);
  });
});

describe('resumerBord : les signalements en attente (F15)', () => {
  it('ne garde que ceux en attente, du plus récent au plus ancien', () => {
    const r = resumer({
      signalements: [
        signalement({ id: 'rep-ancien', submittedAt: '2026-11-20T08:00:00.000Z' }),
        signalement({ id: 'rep-regle', status: 'resolved' }),
        signalement({ id: 'rep-ecarte', status: 'dismissed' }),
        signalement({ id: 'rep-recent', recoId: 'ubm-9', category: 'broken-link', submittedAt: '2026-11-27T10:00:00.000Z' }),
      ],
    });

    expect(r.signalements).toEqual({
      etat: 'lu',
      enAttente: [
        { id: 'rep-recent', recoId: 'ubm-9', categorie: 'broken-link', date: '2026-11-27T10:00:00.000Z' },
        { id: 'rep-ancien', recoId: 'ubm-1', categorie: 'error', date: '2026-11-20T08:00:00.000Z' },
      ],
    });
  });

  it('ne laisse sortir ni le nom, ni l’adresse, ni le texte libre, ni la note', () => {
    const json = JSON.stringify(resumer({ signalements: [signalement()] }));

    for (const interdit of ['Prénom Nom', 'personne@exemple.test', 'Texte libre', 'note de l’éditeur', 'wantCredit']) {
      expect(json).not.toContain(interdit);
    }
  });

  it('dit « inconnu » quand les signalements n’ont pas pu être lus, jamais « rien en attente »', () => {
    expect(resumer({ signalements: null }).signalements).toEqual({ etat: 'inconnu', enAttente: [] });
  });
});
