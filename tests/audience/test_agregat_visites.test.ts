/**
 * Tests de `src/lib/audience/agregat.ts` — ce qui compte comme une visite, le tri
 * en trois colonnes (AU-1 A, B3) et les revenants et le chemin (AU-2 B, D2).
 *
 * Coupé de `test_agregat.test.ts` (tour 1 de revue, PR #224 : fichiers de 500
 * lignes au plus) ; montage dans `_agregat_aide.ts`.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { agreger, estSonde } from '../../src/lib/audience/agregat';
import { AUJOURDHUI, SOURCE, clic, ecrire, effacerLaRacine, installerLaRacine, lire, racine, visite } from './_agregat_aide';

beforeEach(installerLaRacine);
afterEach(effacerLaRacine);

describe('ce qui compte comme une visite', () => {
  it('un préchargement au survol n’est pas une page vue, mais son auteur est un visiteur', () => {
    ecrire('audience', '2026-08-25', [
      visite({ chemin: '/un-bon-moment/films' }),
      visite({ chemin: '/un-bon-moment/oeuvre/a', prechargement: true }),
      visite({ chemin: '/un-bon-moment/oeuvre/b', prechargement: true }),
    ]);
    const a = lire();
    expect(a.pagesVues).toBe(1);
    expect(a.prechargements).toBe(2);
    expect(a.visiteurs).toBe(1);
    expect(a.topPages).toEqual([{ cle: '/un-bon-moment/films', n: 1 }]);
    expect(a.jours[0]).toMatchObject({ pages: 1, visiteurs: 1, prechargements: 2 });
  });

  it('un navigateur qui n’obtient que des erreurs n’est pas un visiteur', () => {
    // Un robot déguisé en navigateur sonde `/wp-login.php` : 404 sur 404.
    ecrire('audience', '2026-08-25', [
      visite({ visiteur: 'humain' }),
      visite({ chemin: '/wp-login.php', statut: 404, visiteur: 'sonde' }),
      visite({ chemin: '/.env', statut: 404, visiteur: 'sonde' }),
    ]);
    const a = lire();
    expect(a.visiteurs).toBe(1);
    expect(a.pagesVues).toBe(1);
    // Des sondes de failles, pas des liens morts : comptées à part.
    expect(a.erreurs404).toHaveLength(0);
    expect(a.sondes).toBe(2);
  });

  it('tient pour robot une requête sans langue', () => {
    // Le 2026-10-22, la moitié des pages vues n'annonçaient aucune langue.
    ecrire('audience', '2026-08-25', [
      visite({ visiteur: 'humain' }),
      visite({ chemin: '/', langue: null, visiteur: 'faux-chrome' }),
    ]);
    const a = lire();
    expect(a.visiteurs).toBe(1);
    expect(a.pagesVues).toBe(1);
    expect(a.visitesRobots).toBe(1);
    expect(a.jours[0]).toMatchObject({ visiteurs: 1, robots: 1 });
  });

  it('garde les vrais liens morts à côté des sondes', () => {
    ecrire('audience', '2026-08-25', [
      visite({ chemin: '/backend/.env', statut: 404 }),
      visite({ chemin: '/xmlrpc.php', statut: 404 }),
      visite({ chemin: '/un-bon-moment/oeuvre/disparue/', statut: 404 }),
      visite({ chemin: '/un-bon-moment/oeuvre/disparue', statut: 404 }),
    ]);
    const a = lire();
    expect(a.erreurs404).toEqual([{ cle: '/un-bon-moment/oeuvre/disparue', n: 2 }]);
    expect(a.sondes).toBe(2);
  });

  it('reconnaît les sondes vues en production le 2026-10-22', () => {
    // Elles occupaient encore toute la liste après le premier filtre.
    for (const chemin of [
      '/_profiler/phpinfo', '/env', '/config/aws.yml', '/docker-compose.yml', '/phpinfo',
      '/config.env', '/config.yaml', '/credentials', '/Dockerfile', '/sendgrid.env',
      '/credentials.ini',
    ]) {
      expect(estSonde(chemin), chemin).toBe(true);
    }
    // Les pages du site, et un vrai lien mort, n'en sont pas.
    for (const chemin of [
      '/', '/mentions-legales', '/un-bon-moment/oeuvre/0099e3e6', '/un-bon-moment/recos',
      '/environnement', '/un-bon-moment/episode/yt-dpM43BlLhZI',
    ]) {
      expect(estSonde(chemin), chemin).toBe(false);
    }
  });

  it('compte /a-propos et /a-propos/ comme une seule page', () => {
    ecrire('audience', '2026-08-25', [
      visite({ chemin: '/a-propos' }),
      visite({ chemin: '/a-propos/' }),
      visite({ chemin: '/' }),
    ]);
    expect(lire().topPages).toEqual([
      { cle: '/a-propos', n: 2 },
      { cle: '/', n: 1 },
    ]);
  });

  it('n’affiche pas le site lui-même dans les provenances', () => {
    // Sans `SITE_URL` au démarrage, le serveur notait chaque clic interne.
    ecrire('audience', '2026-08-25', [
      visite({ provenance: 'unebonnere.co' }),
      visite({ provenance: 'www.unebonnere.co' }),
      visite({ provenance: 'unebonnereco.fr' }),
    ]);
    const a = agreger({
      racine, sourceId: SOURCE, aujourdhui: AUJOURDHUI, hoteDuSite: 'unebonnere.co',
    });
    expect(a.provenances).toEqual([{ cle: 'unebonnereco.fr', n: 1 }]);
  });
});

// ===== Le tri en trois colonnes (AU-1 A, tranche B3) =======================
describe('signaux « page vue » et tri en trois colonnes', () => {
  const NOW = new Date('2026-11-30T12:00:00Z');
  const lireTrois = () => agreger({ racine, sourceId: SOURCE, nbJours: 30, aujourdhui: NOW });
  const nouvelle = (jour: string, over: Record<string, unknown> = {}) =>
    visite({ ts: `${jour}T10:00:00.000Z`, hebergeur: false, ...over });
  const signalDe = (jour: string, over: Record<string, unknown> = {}) => ({
    ts: `${jour}T10:00:00.000Z`,
    nature: 'signal',
    chemin: '/un-bon-moment/films',
    hebergeur: false,
    visiteur: 'aaaaaaaaaaaa',
    ...over,
  });

  it('une ligne de signal ne compte jamais comme visite', () => {
    ecrire('audience', '2026-11-27', [nouvelle('2026-11-27'), signalDe('2026-11-27')]);
    const a = lireTrois();

    expect(a.jours[0].robots).toBe(0);
    expect(a.visitesRobots).toBe(0);
    expect(a.pagesVues).toBe(1);
    expect(a.jours[0].signaux).toBe(1);
    expect(a.topPages).toEqual([{ cle: '/un-bon-moment/films', n: 1 }]);
  });

  it('sans signal : pas de bascule, pas de colonnes, ancien tri', () => {
    ecrire('audience', '2026-11-27', [
      nouvelle('2026-11-27'),
      nouvelle('2026-11-27', { visiteur: 'bbbbbbbbbbbb', hebergeur: true }),
    ]);
    const a = lireTrois();

    expect(a.bascule).toBeNull();
    expect(a.colonnes).toBeNull();
    expect(a.jours[0].colonnes).toBeNull();
    expect(a.jours[0].robots).toBe(0);
    expect(a.panneSignal).toEqual([]);
  });

  it('la bascule est le premier jour complet avec signaux ; avant, l’ancien compte seul', () => {
    ecrire('audience', '2026-11-26', [nouvelle('2026-11-26', { hebergeur: true })]);
    ecrire('audience', '2026-11-27', [nouvelle('2026-11-27'), signalDe('2026-11-27')]);
    ecrire('audience', '2026-11-28', [
      nouvelle('2026-11-28'),
      signalDe('2026-11-28'),
      nouvelle('2026-11-28', { visiteur: 'bbbbbbbbbbbb' }),
      nouvelle('2026-11-28', { visiteur: 'cccccccccccc', hebergeur: true }),
    ]);
    const a = lireTrois();

    expect(a.bascule).toBe('2026-11-28');
    expect(a.jours.map((j) => j.colonnes === null)).toEqual([true, true, false]);
    // Avant la bascule, un hébergeur reste compté comme avant (R-7).
    expect(a.jours[0].robots).toBe(0);
    // Après : confirmé, incertain, et l'hébergeur sans signal est un robot.
    expect(a.jours[2].colonnes).toEqual({
      confirmes: { visiteursJours: 1, visites: 1 },
      incertains: { visiteursJours: 1, visites: 1 },
      robots: { visiteursJours: 1, visites: 1 },
    });
    expect(a.jours[2].robots).toBe(1);
    expect(a.jours[2].visiteurs).toBe(2);
    expect(a.colonnes?.confirmes.visites).toBe(1);
    expect(a.visitesRobots).toBe(1);
  });

  it('avertit quand un jour complet récent a des visites mais aucun signal', () => {
    ecrire('audience', '2026-11-27', [nouvelle('2026-11-27'), signalDe('2026-11-27')]);
    ecrire('audience', '2026-11-28', [nouvelle('2026-11-28'), signalDe('2026-11-28')]);
    const chaque = ['a', 'b', 'c', 'd', 'e'].map((x) =>
      nouvelle('2026-11-29', { visiteur: x.repeat(12) }),
    );
    ecrire('audience', '2026-11-29', chaque);

    expect(lireTrois().panneSignal).toEqual(['2026-11-29']);
  });
});

// ===== Revenants et chemin (AU-2 B, tranche D2) ============================
describe('parcours : revenants et chemin épisode → fiche → clic', () => {
  const NOW = new Date('2026-11-30T12:00:00Z');
  const JOUR = '2026-11-28';
  const lireParcours = () => agreger({ racine, sourceId: SOURCE, nbJours: 30, aujourdhui: NOW });
  const id = (i: number) => `v${String(i).padStart(11, '0')}`;
  const visiteDe = (i: number, jour = JOUR) =>
    visite({ ts: `${jour}T10:00:00.000Z`, hebergeur: false, visiteur: id(i) });
  const signalPour = (i: number, over: Record<string, unknown> = {}, jour = JOUR) => ({
    ts: `${jour}T10:00:00.000Z`, nature: 'signal', chemin: '/un-bon-moment/films', hebergeur: false, visiteur: id(i), ...over,
  });
  // 40 visiteurs confirmés : 12 revenants, tous ont vu un épisode, 15 une fiche.
  const confirmes = (jour = JOUR) => {
    const n = Array.from({ length: 40 }, (_, i) => i);
    return [
      ...n.map((i) => visiteDe(i, jour)),
      ...n.map((i) => signalPour(i, { revenant: i < 12, aVuEpisode: true, aVuFiche: i < 15 }, jour)),
    ];
  };

  it('rend les parts des visiteurs confirmés et des clics', () => {
    ecrire('audience', JOUR, confirmes());
    ecrire('clicks', JOUR, [
      ...Array.from({ length: 12 }, () => clic({ aVuEpisode: true, aVuFiche: true })),
      ...Array.from({ length: 12 }, () => clic({ aVuEpisode: true, aVuFiche: false })),
      ...Array.from({ length: 12 }, () => clic({ aVuEpisode: false, aVuFiche: false })),
      clic(), // ligne d'avant D1 : champs absents, inconnue
    ]);
    const p = lireParcours().parcours;

    expect(p.revenants).toEqual({ oui: 12, total: 40, pct: 30 });
    expect(p.vuFiche).toEqual({ oui: 15, total: 40, pct: 37.5 });
    expect(p.clicsEpisode).toEqual({ oui: 24, total: 36, pct: 66.7 });
    expect(p.clicsFiche).toEqual({ oui: 12, total: 36, pct: 33.3 });
  });

  it('les jours d’avant la bascule et les visiteurs incertains n’y entrent pas', () => {
    // Le jour de bascule est le 2e jour avec signaux : le 27 est écarté, le 28 est compté.
    ecrire('audience', '2026-11-26', [visiteDe(0, '2026-11-26')]);
    ecrire('audience', '2026-11-27', confirmes('2026-11-27'));
    // 10 visiteurs d'hébergeur, avec signal : incertains, donc hors des parts.
    const hebergeurs = Array.from({ length: 10 }, (_, k) => 40 + k);
    ecrire('audience', JOUR, [
      ...confirmes(),
      ...hebergeurs.map((i) => ({ ...visiteDe(i), hebergeur: true })),
      ...hebergeurs.map((i) => signalPour(i, { revenant: true, aVuEpisode: true, aVuFiche: true })),
    ]);
    ecrire('audience', '2026-11-29', confirmes('2026-11-29'));
    const a = lireParcours();

    expect(a.bascule).toBe('2026-11-28');
    // 28 et 29 comptent (12 sur 40 chacun), le 27 non : 36 sur 120 s'il comptait.
    expect(a.parcours.revenants).toEqual({ oui: 24, total: 80, pct: 30 });
  });

  it('trop peu de données : aucune part, sans signal comme sans clic', () => {
    ecrire('audience', JOUR, [visiteDe(0), signalPour(0, { revenant: true })]);
    expect(lireParcours().parcours).toEqual({
      revenants: null, vuFiche: null, clicsEpisode: null, clicsFiche: null,
    });
    expect(lire().parcours.revenants).toBeNull();
  });
});
