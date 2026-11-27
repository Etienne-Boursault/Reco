/**
 * Montage partagé par `test_agregat.test.ts` et `test_agregat_visites.test.ts`
 * (le fichier dépassait 500 lignes : coupé par thème, tour 1 de revue, PR #224).
 *
 * `installerLaRacine` et `effacerLaRacine` se passent à `beforeEach` et
 * `afterEach` dans chaque fichier : un dossier jetable par test.
 */
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { agreger } from '../../src/lib/audience/agregat';

export let racine: string;
export const SOURCE = 'un-bon-moment';
export const AUJOURDHUI = new Date('2026-08-25T12:00:00Z');

export function visite(over: Record<string, unknown> = {}) {
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

export function clic(over: Record<string, unknown> = {}) {
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

export function ecrire(
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

export function lire(nbJours = 30) {
  return agreger({ racine, sourceId: SOURCE, nbJours, aujourdhui: AUJOURDHUI });
}

export const installerLaRacine = () => { racine = mkdtempSync(path.join(tmpdir(), 'reco-agregat-')); };
export const effacerLaRacine = () => rmSync(racine, { recursive: true, force: true });
