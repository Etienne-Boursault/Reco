/**
 * @vitest-environment happy-dom
 *
 * Tests de `src/utils/mesureNavigateur.ts` (AU-2 B, 2026-11-27) : l'état de
 * mesure gardé dans le navigateur (13 mois au plus), les trois oui/non
 * déduits, le refus et la ligne de première visite.
 *
 * Le stockage, l'horloge et `navigator` sont injectés. Le stockage des tests
 * est le vrai `localStorage` de happy-dom, sauf quand il doit lever.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { creerMesure, etapeDuChemin } from '../../src/utils/mesureNavigateur';

const CLE = 'reco.mesure';
const EPISODE = '/ubm/episode/abc';
const FICHE = '/ubm/oeuvre/film-x';

type Nav = { globalPrivacyControl?: boolean; doNotTrack?: string | null };

/** Une mesure sur le `localStorage` de happy-dom, à la date `jour` (UTC). */
function mesureLe(jour: string, navigator: Nav = {}) {
  return creerMesure({
    stockage: () => localStorage,
    maintenant: () => new Date(`${jour}T12:00:00Z`),
    navigator,
  });
}

const lu = () => JSON.parse(localStorage.getItem(CLE) ?? 'null');

beforeEach(() => localStorage.clear());

describe('etapeDuChemin : les chemins réels des pages (src/pages/[source]/…)', () => {
  it('reconnaît une page d’épisode, avec ou sans barre finale', () => {
    expect(etapeDuChemin('/ubm/episode/abc')).toBe('episode');
    expect(etapeDuChemin('/ubm/episode/abc/')).toBe('episode');
  });
  it('reconnaît une fiche œuvre', () => {
    expect(etapeDuChemin('/ubm/oeuvre/film-x')).toBe('fiche');
    expect(etapeDuChemin('/ubm/oeuvre/film-x/')).toBe('fiche');
  });
  it('rend null pour tout le reste', () => {
    for (const c of ['/', '/ubm', '/ubm/episode', '/ubm/episode/', '/ubm/episode/a/b', '/ubm/invite/x', '/ubm/oeuvres', '/episode/abc', '/a-propos']) {
      expect(etapeDuChemin(c)).toBeNull();
    }
  });
});

describe('naissance et revenant', () => {
  it('la première page crée l’état, sans revenant', () => {
    expect(mesureLe('2026-11-27').noterPage('/ubm')).toEqual({ revenant: false, aVuEpisode: false, aVuFiche: false });
    expect(lu()).toMatchObject({ ne: '2026-11-27' });
  });

  it('une seconde page le même jour ne rend pas revenant', () => {
    mesureLe('2026-11-27').noterPage('/ubm');
    expect(mesureLe('2026-11-27').noterPage('/ubm')?.revenant).toBe(false);
  });

  it('un autre jour rend revenant, sans jamais réécrire la naissance', () => {
    mesureLe('2026-11-27').noterPage('/ubm');
    expect(mesureLe('2026-11-28').noterPage('/ubm')?.revenant).toBe(true);
    expect(mesureLe('2027-06-01').noterPage('/ubm')?.revenant).toBe(true);
    expect(lu().ne).toBe('2026-11-27');
  });
});

describe('étapes du jour', () => {
  it('note l’épisode et la fiche, page courante comprise', () => {
    const m = mesureLe('2026-11-27');
    expect(m.noterPage(EPISODE)).toMatchObject({ aVuEpisode: true, aVuFiche: false });
    expect(m.noterPage(FICHE)).toMatchObject({ aVuEpisode: true, aVuFiche: true });
    expect(m.noterPage('/ubm')).toMatchObject({ aVuEpisode: true, aVuFiche: true });
    expect(m.noterPage(FICHE)).toMatchObject({ aVuFiche: true });
    expect(lu().etapes).toEqual(['episode', 'fiche']);
  });

  it('les étapes ne survivent pas au jour', () => {
    mesureLe('2026-11-27').noterPage(EPISODE);
    expect(mesureLe('2026-11-28').noterPage('/ubm')).toMatchObject({ revenant: true, aVuEpisode: false, aVuFiche: false });
    expect(lu().etapes).toEqual([]);
  });
});

describe('fin à 13 mois, état recréé neuf', () => {
  const ne = (date: string) => localStorage.setItem(CLE, JSON.stringify({ ne: date, jour: date, etapes: ['episode'], ligne: 2 }));

  it('la veille des 13 mois, l’état est gardé tel quel', () => {
    ne('2025-10-27');
    expect(mesureLe('2026-11-26').noterPage('/ubm')?.revenant).toBe(true);
    expect(lu().ne).toBe('2025-10-27');
  });

  it('le jour des 13 mois, tout repart de zéro', () => {
    ne('2025-10-27');
    expect(mesureLe('2026-11-27').noterPage('/ubm')).toEqual({ revenant: false, aVuEpisode: false, aVuFiche: false });
    expect(lu()).toMatchObject({ ne: '2026-11-27', etapes: [], ligne: 0 });
  });

  it('un 31 janvier finit le dernier jour de février, 13 mois plus tard', () => {
    ne('2025-01-31');
    expect(mesureLe('2026-02-27').noterPage('/ubm')?.revenant).toBe(true);
    expect(mesureLe('2026-02-28').noterPage('/ubm')?.revenant).toBe(false);
    expect(lu().ne).toBe('2026-02-28');
  });

  it('un 29 février finit le 29 mars de l’année d’après', () => {
    ne('2024-02-29');
    expect(mesureLe('2025-03-28').noterPage('/ubm')?.revenant).toBe(true);
    expect(mesureLe('2025-03-29').noterPage('/ubm')?.revenant).toBe(false);
  });

  it('un autre mois que janvier garde le même quantième', () => {
    ne('2025-05-15');
    expect(mesureLe('2026-06-14').noterPage('/ubm')?.revenant).toBe(true);
    expect(mesureLe('2026-06-15').noterPage('/ubm')?.revenant).toBe(false);
  });
});

describe('état illisible ou invalide : recréé neuf', () => {
  const cas: Record<string, string> = {
    'naissance dans le futur': JSON.stringify({ ne: '2026-11-28' }),
    'naissance absente': JSON.stringify({ ligne: 1 }),
    'naissance qui n’est pas une date': JSON.stringify({ ne: 'hier' }),
    'jour qui n’existe pas': JSON.stringify({ ne: '2026-02-30' }),
    'JSON cassé': '{ne:',
    'valeur qui n’est pas un objet': '42',
    'JSON null': 'null',
    'refus qui n’est pas vrai': JSON.stringify({ refus: 'oui' }),
  };
  for (const [nom, brut] of Object.entries(cas)) {
    it(nom, () => {
      localStorage.setItem(CLE, brut);
      expect(mesureLe('2026-11-27').noterPage('/ubm')?.revenant).toBe(false);
      expect(lu()).toMatchObject({ ne: '2026-11-27', ligne: 0 });
    });
  }

  it('étapes et ligne corrompues : filtrées, pas de plantage', () => {
    localStorage.setItem(CLE, JSON.stringify({ ne: '2026-11-20', jour: '2026-11-27', etapes: ['episode', 'x', 3, 'episode'], ligne: 'a' }));
    const m = mesureLe('2026-11-27');
    expect(m.noterPage('/ubm')).toEqual({ revenant: true, aVuEpisode: true, aVuFiche: false });
    expect(lu().etapes).toEqual(['episode']);
    expect(m.ligneAAfficher()).toBe(false);
  });

  it('étapes qui ne sont pas une liste : ignorées', () => {
    localStorage.setItem(CLE, JSON.stringify({ ne: '2026-11-20', jour: '2026-11-27', etapes: 'episode', ligne: 0 }));
    expect(mesureLe('2026-11-27').noterPage('/ubm')?.aVuEpisode).toBe(false);
  });

  it('ligne hors bornes ramenée dans 0 à 2', () => {
    localStorage.setItem(CLE, JSON.stringify({ ne: '2026-11-20', ligne: -5 }));
    expect(mesureLe('2026-11-27').ligneAAfficher()).toBe(true);
    localStorage.setItem(CLE, JSON.stringify({ ne: '2026-11-20', ligne: 9 }));
    expect(mesureLe('2026-11-27').ligneAAfficher()).toBe(false);
  });
});

describe('refus (R-2)', () => {
  it('refuser efface tout et ne garde que le choix, sans échéance', () => {
    const m = mesureLe('2026-11-27');
    m.noterPage(EPISODE);
    expect(m.refuser()).toBe('refusee');
    expect(lu()).toEqual({ refus: true });
    expect(mesureLe('2030-01-01').etat()).toBe('refusee');
  });

  it('sous refus, il ne faut rien envoyer ni rien stocker', () => {
    const m = mesureLe('2026-11-27');
    m.refuser();
    expect(m.noterPage(EPISODE)).toBeNull();
    expect(lu()).toEqual({ refus: true });
    expect(m.ligneAAfficher()).toBe(false);
  });

  it('accepter repart d’un état neuf, sans remontrer la ligne', () => {
    const m = mesureLe('2026-11-27');
    m.noterPage(EPISODE);
    m.refuser();
    expect(m.accepter()).toBe('active');
    expect(lu()).toEqual({ ne: '2026-11-27', jour: '2026-11-27', etapes: [], ligne: 2 });
    expect(m.ligneAAfficher()).toBe(false);
    expect(mesureLe('2026-11-28').noterPage('/ubm')?.revenant).toBe(true);
  });
});

describe('GPC et DNT : rien n’est envoyé ni stocké', () => {
  for (const [nom, nav] of [
    ['GPC', { globalPrivacyControl: true }],
    ['DNT', { doNotTrack: '1' }],
  ] as const) {
    it(`${nom} : état « navigateur », rien envoyé, rien stocké`, () => {
      const m = mesureLe('2026-11-27', nav);
      expect(m.etat()).toBe('navigateur');
      expect(m.noterPage(EPISODE)).toBeNull();
      expect(localStorage.getItem(CLE)).toBeNull();
      expect(m.ligneAAfficher()).toBe(false);
    });

    it(`${nom} : efface l’état gardé avant, et garde le refus s’il y en avait un`, () => {
      mesureLe('2026-11-27').noterPage(EPISODE);
      mesureLe('2026-11-27', nav).noterPage(EPISODE);
      expect(localStorage.getItem(CLE)).toBeNull();

      mesureLe('2026-11-27').refuser();
      mesureLe('2026-11-27', nav).noterPage(EPISODE);
      expect(lu()).toEqual({ refus: true });
    });

    it(`${nom} : ni « Refuser » ni « Réactiver » n’y changent rien`, () => {
      const m = mesureLe('2026-11-27', nav);
      expect(m.refuser()).toBe('navigateur');
      expect(m.accepter()).toBe('navigateur');
      expect(localStorage.getItem(CLE)).toBeNull();
    });
  }

  it('DNT à « 0 » laisse passer', () => {
    expect(mesureLe('2026-11-27', { doNotTrack: '0' }).etat()).toBe('active');
  });
});

describe('la ligne de première visite (R-13)', () => {
  it('s’affiche sur deux pages, puis disparaît', () => {
    const m = mesureLe('2026-11-27');
    m.noterPage('/ubm');
    expect(m.ligneAAfficher()).toBe(true);
    m.ligneVue();
    m.noterPage('/ubm');
    expect(m.ligneAAfficher()).toBe(true);
    m.ligneVue();
    m.noterPage('/ubm');
    expect(m.ligneAAfficher()).toBe(false);
    m.ligneVue();
    expect(lu().ligne).toBe(2);
  });

  it('ne s’affiche pas avant que la première page ait créé l’état', () => {
    const m = mesureLe('2026-11-27');
    expect(m.ligneAAfficher()).toBe(false);
    m.ligneVue();
    m.fermerLigne();
    expect(localStorage.getItem(CLE)).toBeNull();
  });

  it('« OK » la ferme tout de suite', () => {
    const m = mesureLe('2026-11-27');
    m.noterPage('/ubm');
    m.fermerLigne();
    expect(m.ligneAAfficher()).toBe(false);
  });

  it('« Refuser » la ferme et l’interrupteur la rejoint', () => {
    const m = mesureLe('2026-11-27');
    m.noterPage('/ubm');
    m.refuser();
    expect(m.ligneAAfficher()).toBe(false);
    expect(m.etat()).toBe('refusee');
  });

  it('deux onglets ouverts ensemble : un seul état, pas plus de deux pages', () => {
    const a = mesureLe('2026-11-27');
    const b = mesureLe('2026-11-27');
    a.noterPage('/ubm');
    b.noterPage('/ubm');
    const naissance = lu().ne;
    expect(a.ligneAAfficher()).toBe(true);
    expect(b.ligneAAfficher()).toBe(true);
    a.ligneVue();
    b.ligneVue();
    expect(lu().ne).toBe(naissance);
    expect(a.ligneAAfficher()).toBe(false);
    expect(b.ligneAAfficher()).toBe(false);
  });

  it('un clic dans un onglet la ferme dans l’autre', () => {
    const a = mesureLe('2026-11-27');
    const b = mesureLe('2026-11-27');
    a.noterPage('/ubm');
    b.noterPage('/ubm');
    a.fermerLigne();
    expect(b.ligneAAfficher()).toBe(false);
  });
});

describe('stockage qui lève : la page ne casse jamais', () => {
  const sansStockage = (stockage: () => Storage) =>
    creerMesure({ stockage, maintenant: () => new Date('2026-11-27T12:00:00Z'), navigator: {} });
  const leve = () => {
    throw new Error('SecurityError');
  };

  it('accès au stockage interdit : état « indisponible », signal sans état gardé', () => {
    const m = sansStockage(leve);
    expect(m.etat()).toBe('indisponible');
    expect(m.noterPage(EPISODE)).toEqual({ revenant: false, aVuEpisode: true, aVuFiche: false });
    expect(m.noterPage(FICHE)).toEqual({ revenant: false, aVuEpisode: false, aVuFiche: true });
    expect(m.ligneAAfficher()).toBe(false);
    expect(() => {
      m.ligneVue();
      m.fermerLigne();
    }).not.toThrow();
    expect(m.refuser()).toBe('indisponible');
    expect(m.accepter()).toBe('indisponible');
  });

  it('GPC sans stockage : rien n’est envoyé et rien ne lève', () => {
    const m = creerMesure({ stockage: leve, maintenant: () => new Date(), navigator: { globalPrivacyControl: true } });
    expect(m.noterPage(EPISODE)).toBeNull();
  });

  it('écriture refusée (quota) : on répond quand même, sans exception', () => {
    const plein = {
      getItem: () => null,
      setItem: leve,
      removeItem: leve,
      clear: () => {},
      key: () => null,
      length: 0,
    } as Storage;
    const m = sansStockage(() => plein);
    expect(m.noterPage(FICHE)).toEqual({ revenant: false, aVuEpisode: false, aVuFiche: true });
    expect(m.ligneAAfficher()).toBe(false);
    expect(() => {
      m.refuser();
      m.accepter();
    }).not.toThrow();
  });
});

describe('ouiNon : lecture seule pour le clic sortant (D1, R-1)', () => {
  it('sans état : null, et rien n’est créé', () => {
    expect(mesureLe('2026-11-27').ouiNon(FICHE)).toBeNull();
    expect(localStorage.getItem(CLE)).toBeNull();
  });

  it('rend les trois oui/non du jour, la page courante comptée, sans rien écrire', () => {
    mesureLe('2026-11-20').noterPage(EPISODE);
    // Le lendemain, le signal n'est pas encore parti : seule la page courante compte.
    const m = mesureLe('2026-11-27');
    const avant = localStorage.getItem(CLE);
    expect(m.ouiNon(FICHE)).toEqual({ revenant: true, aVuEpisode: false, aVuFiche: true });
    expect(localStorage.getItem(CLE)).toBe(avant);
  });

  it('reprend les étapes déjà vues le jour même', () => {
    const m = mesureLe('2026-11-27');
    m.noterPage(EPISODE);
    expect(m.ouiNon(FICHE)).toEqual({ revenant: false, aVuEpisode: true, aVuFiche: true });
    expect(m.ouiNon('/ubm/invite/x')).toEqual({ revenant: false, aVuEpisode: true, aVuFiche: false });
  });

  it('refus, GPC, DNT : null', () => {
    const m = mesureLe('2026-11-27');
    m.noterPage(EPISODE);
    m.refuser();
    expect(m.ouiNon(FICHE)).toBeNull();
    expect(mesureLe('2026-11-27', { globalPrivacyControl: true }).ouiNon(FICHE)).toBeNull();
    expect(mesureLe('2026-11-27', { doNotTrack: '1' }).ouiNon(FICHE)).toBeNull();
  });

  it('stockage qui lève : null, sans exception', () => {
    const m = creerMesure({
      stockage: () => {
        throw new Error('coupé');
      },
      maintenant: () => new Date(),
      navigator: {},
    });
    expect(m.ouiNon(FICHE)).toBeNull();
  });
});
