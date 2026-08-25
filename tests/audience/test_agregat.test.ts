/**
 * Tests de `src/lib/audience/agregat.ts` — la lecture des mesures.
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * Un tableau de bord ment plus facilement qu'il ne se trompe : un chiffre
 * plausible mais faux ne déclenche aucune alerte. Ces tests fixent donc les
 * définitions plutôt que les valeurs — ce qui compte comme page vue, ce qui
 * compte comme visiteur, et surtout ce qui n'est jamais recousu.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { agreger, sourcesDisponibles } from '../../src/lib/audience/agregat';

let racine: string;
const SOURCE = 'un-bon-moment';
const AUJOURDHUI = new Date('2026-08-25T12:00:00Z');

function visite(over: Record<string, unknown> = {}) {
  return {
    ts: '2026-08-25T10:00:00.000Z',
    chemin: '/un-bon-moment/films',
    statut: 200,
    robot: false,
    appareil: 'ordinateur',
    provenance: null,
    langue: 'fr',
    pays: null,
    visiteur: 'aaaaaaaaaaaa',
    dureeMs: 20,
    ...over,
  };
}

function clic(over: Record<string, unknown> = {}) {
  return {
    ts: '2026-08-25T10:05:00.000Z',
    url: 'https://www.themoviedb.org/movie/1',
    category: 'tmdb',
    sourceId: SOURCE,
    recoId: 'ubm-1',
    ref: '/un-bon-moment/films',
    ...over,
  };
}

function ecrire(
  genre: 'audience' | 'clicks',
  jour: string,
  lignes: unknown[],
  source = SOURCE,
) {
  const dossier = path.join(racine, 'tools', 'output', genre, source);
  mkdirSync(dossier, { recursive: true });
  writeFileSync(
    path.join(dossier, `${jour}.jsonl`),
    lignes.map((l) => JSON.stringify(l)).join('\n') + '\n',
    'utf8',
  );
}

function lire(nbJours = 30) {
  return agreger({ racine, sourceId: SOURCE, nbJours, aujourdhui: AUJOURDHUI });
}

beforeEach(() => { racine = mkdtempSync(path.join(tmpdir(), 'reco-agregat-')); });
afterEach(() => rmSync(racine, { recursive: true, force: true }));

// ===== Sans données ========================================================
describe('sans aucune mesure', () => {
  it('rend un agrégat vide plutôt que d’échouer', () => {
    // Le premier jour après la mise en ligne, il n'y a rien à lire.
    const a = lire();

    expect(a.pagesVues).toBe(0);
    expect(a.visiteurs).toBe(0);
    expect(a.du).toBeNull();
    expect(a.jours).toEqual([]);
    expect(a.clicsParVisiteur).toBeNull();
  });

  it('ne prétend pas que le pays est indisponible quand rien n’est mesuré', () => {
    // Distinguer « pas de données » de « données sans pays » : le tableau de
    // bord n'affichera un avertissement que dans le second cas.
    expect(lire().paysIndisponible).toBe(false);
  });
});

// ===== Ce qui compte =======================================================
describe('définitions', () => {
  it('ne compte PAS les robots dans les pages vues', () => {
    // Sur un catalogue de 2 600 pages, les moteurs font souvent l'essentiel du
    // trafic : les mêler à l'audience rendrait tous les chiffres faux.
    ecrire('audience', '2026-08-25', [
      visite(),
      visite({ robot: true, visiteur: 'bbbbbbbbbbbb' }),
      visite({ robot: true, visiteur: 'cccccccccccc' }),
    ]);
    const a = lire();

    expect(a.pagesVues).toBe(1);
    expect(a.visitesRobots).toBe(2);
  });

  it('compte un visiteur une seule fois, quel que soit le nombre de pages', () => {
    ecrire('audience', '2026-08-25', [
      visite({ chemin: '/a' }),
      visite({ chemin: '/b' }),
      visite({ chemin: '/c' }),
    ]);
    const a = lire();

    expect(a.pagesVues).toBe(3);
    expect(a.visiteurs).toBe(1);
  });

  it('ne recoud JAMAIS deux jours', () => {
    // Le sel change de portée chaque jour : le même appareil a deux
    // identifiants différents. Les additionner serait la seule façon de
    // reconstituer un suivi dans le temps — on ne le fait pas.
    ecrire('audience', '2026-08-24', [visite({ ts: '2026-08-24T10:00:00.000Z', visiteur: 'jour1abc' })]);
    ecrire('audience', '2026-08-25', [visite({ visiteur: 'jour2xyz' })]);
    const a = lire();

    expect(a.visiteurs).toBe(2);
    expect(a.jours.map((j) => j.visiteurs)).toEqual([1, 1]);
  });

  it('ne compte pas un visiteur sans identifiant', () => {
    // Sans sel configuré, `visiteur` vaut null : les pages sont comptées, pas
    // les visiteurs. Un zéro honnête vaut mieux qu'un chiffre inventé.
    ecrire('audience', '2026-08-25', [visite({ visiteur: null }), visite({ visiteur: null })]);
    const a = lire();

    expect(a.pagesVues).toBe(2);
    expect(a.visiteurs).toBe(0);
  });
});

// ===== Clics par visiteur =================================================
describe('clics par visiteur', () => {
  it('rapporte les clics aux visiteurs, pas aux pages', () => {
    // Cliquer une fois par visite suffit à avoir découvert quelque chose.
    ecrire('audience', '2026-08-25', [
      visite({ chemin: '/a' }),
      visite({ chemin: '/b' }),
      visite({ visiteur: 'deuxieme-vis' }),
      visite({ visiteur: 'troisieme-vi' }),
      visite({ visiteur: 'quatrieme-vi' }),
    ]);
    ecrire('clicks', '2026-08-25', [clic(), clic(), clic()]);

    // 4 visiteurs, 3 clics.
    expect(lire().clicsParVisiteur).toBe(0.8);
  });

  it('peut dépasser 1 : ce n’est PAS un pourcentage', () => {
    // Le premier jet l'affichait comme un « taux de découverte » et sortait
    // 664 % sur un jeu d'essai. Un visiteur peut cliquer plusieurs fois, et
    // relier un clic à un visiteur est justement ce qu'on refuse de faire.
    ecrire('audience', '2026-08-25', [visite()]);
    ecrire('clicks', '2026-08-25', [clic(), clic(), clic(), clic(), clic()]);

    expect(lire().clicsParVisiteur).toBe(5);
  });

  it('rend null sans visiteur : une division n’est pas une mesure', () => {
    ecrire('clicks', '2026-08-25', [clic()]);
    expect(lire().clicsParVisiteur).toBeNull();
  });
});

// ===== Plusieurs sources ==================================================
describe('plusieurs sources', () => {
  it('agrège les sources demandées en une seule vue', () => {
    // `sourceDuChemin` range sous `_site` tout ce qui ne commence pas par un
    // segment de source connue : l'ACCUEIL et les 404. Un tableau de bord qui
    // ne lirait qu'`un-bon-moment` cacherait donc la page d'entrée du site et
    // tous ses liens morts — vérifié en production le 2026-08-25, où il
    // affichait « aucune page demandée en vain » alors que `_site` en portait
    // trois.
    ecrire('audience', '2026-08-25', [visite({ chemin: '/un-bon-moment/films' })]);
    ecrire('audience', '2026-08-25', [
      visite({ chemin: '/', visiteur: 'venu-de-la-ra' }),
      visite({ chemin: '/lien-mort', statut: 404, visiteur: 'venu-de-la-ra' }),
    ], '_site');

    const a = agreger({ racine, sourceId: [SOURCE, '_site'], nbJours: 30, aujourdhui: AUJOURDHUI });

    expect(a.pagesVues).toBe(3);
    expect(a.visiteurs).toBe(2);
    expect(a.topPages.map((p) => p.cle)).toContain('/');
    expect(a.erreurs404[0]).toEqual({ cle: '/lien-mort', n: 1 });
  });

  it('additionne les clics de toutes les sources', () => {
    ecrire('clicks', '2026-08-25', [clic()]);
    ecrire('clicks', '2026-08-25', [clic()], 'autre-podcast');

    expect(agreger({ racine, sourceId: [SOURCE, 'autre-podcast'], nbJours: 30, aujourdhui: AUJOURDHUI }).clics).toBe(2);
  });

  it('compte une seule fois un visiteur vu sur deux sources', () => {
    // Même appareil, même jour, même identifiant : c'est UNE personne qui a
    // traversé deux rubriques, pas deux visiteurs.
    ecrire('audience', '2026-08-25', [visite()]);
    ecrire('audience', '2026-08-25', [visite({ chemin: '/' })], '_site');

    const a = agreger({ racine, sourceId: [SOURCE, '_site'], nbJours: 30, aujourdhui: AUJOURDHUI });

    expect(a.pagesVues).toBe(2);
    expect(a.visiteurs).toBe(1);
  });

  it('accepte encore une source unique en chaîne', () => {
    // La signature d'origine reste valable : les appels existants ne cassent pas.
    ecrire('audience', '2026-08-25', [visite()]);
    expect(lire().pagesVues).toBe(1);
  });
});

describe('sourcesDisponibles', () => {
  it('liste les dossiers des visites ET des clics, sans doublon', () => {
    ecrire('audience', '2026-08-25', [visite()]);
    ecrire('clicks', '2026-08-25', [clic()]);
    ecrire('audience', '2026-08-25', [visite()], '_site');
    ecrire('clicks', '2026-08-25', [clic()], 'podcast-sans-visite');

    expect(sourcesDisponibles(racine)).toEqual(['_site', 'podcast-sans-visite', SOURCE]);
  });

  it('rend une liste vide quand rien n’a encore été mesuré', () => {
    expect(sourcesDisponibles(racine)).toEqual([]);
  });
});

// ===== Les classements ====================================================
describe('classements', () => {
  it('classe les pages consultées, en écartant les erreurs', () => {
    // Une page qui répond 404 n'est pas une page consultée.
    ecrire('audience', '2026-08-25', [
      visite({ chemin: '/populaire' }),
      visite({ chemin: '/populaire' }),
      visite({ chemin: '/rare' }),
      visite({ chemin: '/disparue', statut: 404 }),
    ]);
    const a = lire();

    expect(a.topPages[0]).toEqual({ cle: '/populaire', n: 2 });
    expect(a.topPages.map((p) => p.cle)).not.toContain('/disparue');
  });

  it('classe les 404 : ce sont les liens périmés qui circulent', () => {
    ecrire('audience', '2026-08-25', [
      visite({ chemin: '/fiche-fusionnee', statut: 404 }),
      visite({ chemin: '/fiche-fusionnee', statut: 404 }),
    ]);

    expect(lire().erreurs404[0]).toEqual({ cle: '/fiche-fusionnee', n: 2 });
  });

  it('compte les 404 des robots aussi', () => {
    // Un lien mort reste un lien mort, même découvert par un moteur.
    ecrire('audience', '2026-08-25', [visite({ chemin: '/x', statut: 404, robot: true })]);

    expect(lire().erreurs404[0]).toEqual({ cle: '/x', n: 1 });
  });

  it('classe les provenances et ignore les valeurs absentes', () => {
    ecrire('audience', '2026-08-25', [
      visite({ provenance: 'www.google.com' }),
      visite({ provenance: 'www.google.com' }),
      visite({ provenance: null }),
    ]);
    const a = lire();

    expect(a.provenances).toEqual([{ cle: 'www.google.com', n: 2 }]);
  });

  it('classe les plateformes cliquées', () => {
    // La mesure qui dit si le parti pris éthique fonctionne.
    ecrire('clicks', '2026-08-25', [
      clic({ category: 'bandcamp' }),
      clic({ category: 'bandcamp' }),
      clic({ category: 'tmdb' }),
    ]);

    expect(lire().plateformes[0]).toEqual({ cle: 'bandcamp', n: 2 });
  });
});

// ===== Le pays ============================================================
describe('pays', () => {
  it('signale l’indisponibilité quand aucune visite n’en porte', () => {
    // L'hébergeur ne pose peut-être aucun en-tête de géolocalisation : le
    // tableau de bord doit le dire plutôt que d'afficher un vide ambigu.
    ecrire('audience', '2026-08-25', [visite({ pays: null }), visite({ pays: null })]);
    const a = lire();

    expect(a.paysIndisponible).toBe(true);
    expect(a.paysConnus).toEqual([]);
  });

  it('classe les pays dès qu’un seul est connu', () => {
    ecrire('audience', '2026-08-25', [visite({ pays: 'FR' }), visite({ pays: null })]);
    const a = lire();

    expect(a.paysIndisponible).toBe(false);
    expect(a.paysConnus).toEqual([{ cle: 'FR', n: 1 }]);
  });
});

// ===== La fenêtre =========================================================
describe('fenêtre temporelle', () => {
  it('ignore ce qui précède la fenêtre demandée', () => {
    ecrire('audience', '2026-07-01', [visite({ ts: '2026-07-01T10:00:00.000Z' })]);
    ecrire('audience', '2026-08-25', [visite()]);
    const a = lire(7);

    expect(a.pagesVues).toBe(1);
    expect(a.du).toBe('2026-08-25');
  });

  it('rend les jours dans l’ordre chronologique', () => {
    ecrire('audience', '2026-08-23', [visite({ ts: '2026-08-23T10:00:00.000Z' })]);
    ecrire('audience', '2026-08-25', [visite()]);

    expect(lire().jours.map((j) => j.jour)).toEqual(['2026-08-23', '2026-08-25']);
  });
});

// ===== Robustesse =========================================================
describe('robustesse', () => {
  it('ignore une ligne corrompue sans perdre les autres', () => {
    // Une coupure au milieu d'une écriture ne doit pas rendre la journée
    // illisible.
    const dossier = path.join(racine, 'tools', 'output', 'audience', SOURCE);
    mkdirSync(dossier, { recursive: true });
    writeFileSync(
      path.join(dossier, '2026-08-25.jsonl'),
      `${JSON.stringify(visite())}\n{ ligne tronqu\n${JSON.stringify(visite({ chemin: '/b' }))}\n`,
      'utf8',
    );

    expect(lire().pagesVues).toBe(2);
  });

  it('supporte des clics sans visites, et l’inverse', () => {
    ecrire('clicks', '2026-08-25', [clic()]);
    const a = lire();

    expect(a.clics).toBe(1);
    expect(a.pagesVues).toBe(0);
  });

  it('calcule une durée médiane, ou null', () => {
    ecrire('audience', '2026-08-25', [
      visite({ dureeMs: 10 }), visite({ dureeMs: 20 }), visite({ dureeMs: 90 }),
    ]);
    expect(lire().dureeMedianeMs).toBe(20);
  });
});
