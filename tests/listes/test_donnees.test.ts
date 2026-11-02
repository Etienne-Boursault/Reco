/**
 * Lecture des playlists et des listes SensCritique (`src/lib/listes/donnees.ts`).
 *
 * Les fichiers de `tools/data/` sont une frontière : on vérifie que ce qui n'a
 * pas la forme attendue est écarté, et que la lecture réelle du dépôt donne
 * bien des listes pour `un-bon-moment`, et rien pour une autre source.
 */
import { afterEach, describe, expect, it } from 'vitest';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  chargerListes,
  listeDuGenre,
  lirePlaylists,
  lireSensCritique,
  nombreDeListes,
  playlistDeLaSaison,
  viderCacheListes,
  type Listes,
} from '../../src/lib/listes/donnees';

const p = (id: string | number, n: number) => ({ id, titres: Array.from({ length: n }, (_, i) => `t${i}`) });

describe('lirePlaylists', () => {
  it('garde les playlists présentes sur les deux plateformes, saisons récentes d’abord', () => {
    const r = lirePlaylists(
      { playlists: { 'Saison 1': p('a1', 3), 'Toutes les recos musicales': p('aT', 9), 'Saison 2': p('a2', 4) } },
      { playlists: { 'Saison 1': p(111, 3), 'Saison 2': p(222, 5), 'Toutes les recos musicales': p(999, 9) } },
    );
    expect(r.toutes).toEqual({
      nom: 'Toutes les recos musicales',
      saison: null,
      spotify: 'https://open.spotify.com/playlist/aT',
      deezer: 'https://www.deezer.com/fr/playlist/999',
      titres: { spotify: 9, deezer: 9 },
    });
    expect(r.saisons.map((s) => s.saison)).toEqual([2, 1]);
    expect(r.saisons[0].titres).toEqual({ spotify: 4, deezer: 5 });
  });

  it('écarte une playlist d’un seul côté, un nom inconnu, un identifiant douteux', () => {
    const r = lirePlaylists(
      {
        playlists: {
          'Saison 3': p('ok', 1),
          'Saisons 1 à 4 (2020-2024)': p('vieux', 2),
          'Saison 4': p('../piege', 1),
          'Saison 5': { id: 'sanstitres' },
          'Saison 6': p('seul', 1),
        },
      },
      { playlists: { 'Saison 3': p('d3', 1), 'Saisons 1 à 4 (2020-2024)': p('d', 2), 'Saison 4': p('d4', 1), 'Saison 5': p('d5', 1) } },
    );
    expect(r.toutes).toBeNull();
    expect(r.saisons.map((s) => s.nom)).toEqual(['Saison 3']);
  });

  it('tolère des fichiers absents ou malformés', () => {
    expect(lirePlaylists(null, undefined)).toEqual({ toutes: null, saisons: [] });
    expect(lirePlaylists({ playlists: [] }, 'texte')).toEqual({ toutes: null, saisons: [] });
    expect(lirePlaylists({ playlists: { 'Saison 1': null } }, { playlists: { 'Saison 1': p('x', 1) } }).saisons).toEqual([]);
  });
});

describe('lireSensCritique', () => {
  it('lit les listes valides dans l’ordre film, série, livre, BD', () => {
    const r = lireSensCritique({
      listes: {
        bd: { url: 'https://www.senscritique.com/liste/bd/4', ajoutees: ['b1', 7, 'b2'], traitees: ['x'] },
        film: { url: 'https://www.senscritique.com/liste/films/1', ajoutees: ['f1'] },
      },
    });
    expect(r).toEqual([
      { genre: 'film', url: 'https://www.senscritique.com/liste/films/1', oeuvres: ['f1'] },
      { genre: 'bd', url: 'https://www.senscritique.com/liste/bd/4', oeuvres: ['b1', 'b2'] },
    ]);
  });

  it('attache la liste « évoqués » à la liste « recommandés » du même genre', () => {
    const r = lireSensCritique({
      listes: {
        film: { url: 'https://www.senscritique.com/liste/films/1', ajoutees: ['f1'] },
        serie: { url: 'https://www.senscritique.com/liste/series/2', ajoutees: [] },
      },
      evoquees: {
        film: { url: 'https://www.senscritique.com/liste/films_evoques/5', ajoutees: ['f2', 'f3'] },
        serie: { url: 'https://exemple.com/x', ajoutees: [] },
        bd: { url: 'https://www.senscritique.com/liste/bd_evoquees/8', ajoutees: ['b'] },
      },
    });
    expect(r).toEqual([
      {
        genre: 'film',
        url: 'https://www.senscritique.com/liste/films/1',
        oeuvres: ['f1'],
        evoquees: { url: 'https://www.senscritique.com/liste/films_evoques/5', oeuvres: ['f2', 'f3'] },
      },
      { genre: 'serie', url: 'https://www.senscritique.com/liste/series/2', oeuvres: [] },
    ]);
  });

  it('écarte une adresse hors SensCritique ou une liste sans `ajoutees`', () => {
    expect(
      lireSensCritique({
        listes: {
          film: { url: 'https://exemple.com/liste/1', ajoutees: [] },
          serie: { url: 'https://www.senscritique.com/liste/s/2' },
          livre: { url: 42, ajoutees: [] },
          bd: 'rien',
        },
      }),
    ).toEqual([]);
    expect(lireSensCritique(null)).toEqual([]);
  });
});

describe('chargerListes', () => {
  let dossier = '';
  afterEach(() => {
    viderCacheListes();
    if (dossier) rmSync(dossier, { recursive: true, force: true });
    dossier = '';
  });

  function depot(fichiers: Record<string, string>): string {
    dossier = mkdtempSync(join(tmpdir(), 'listes-'));
    mkdirSync(join(dossier, 'tools', 'data'), { recursive: true });
    for (const [nom, contenu] of Object.entries(fichiers)) writeFileSync(join(dossier, 'tools', 'data', nom), contenu);
    return dossier;
  }

  it('rien pour une source sans listes, ou sans source', () => {
    expect(chargerListes('autre-podcast')).toBeNull();
    expect(chargerListes(undefined)).toBeNull();
  });

  it('lit les trois fichiers de la source et garde le résultat en cache', () => {
    const racine = depot({
      'playlists_spotify.json': JSON.stringify({ playlists: { 'Saison 2': p('s2', 2) } }),
      'playlists_deezer.json': JSON.stringify({ playlists: { 'Saison 2': p(2, 2) } }),
      'senscritique.json': '{ illisible',
    });
    const l = chargerListes('un-bon-moment', racine);
    expect(l?.saisons).toHaveLength(1);
    expect(l?.senscritique).toEqual([]);
    rmSync(join(racine, 'tools'), { recursive: true });
    expect(chargerListes('un-bon-moment', racine)).toBe(l);
  });

  it('aucune liste lisible → null (et null mis en cache)', () => {
    const racine = depot({});
    expect(chargerListes('un-bon-moment', racine)).toBeNull();
    expect(chargerListes('un-bon-moment', racine)).toBeNull();
  });

  it('le dépôt réel : les nombres affichés sont ceux des fichiers', () => {
    const l = chargerListes('un-bon-moment') as Listes;
    const brut = JSON.parse(readFileSync('tools/data/playlists_spotify.json', 'utf-8'));
    const sc = JSON.parse(readFileSync('tools/data/senscritique.json', 'utf-8'));
    expect(l.toutes?.titres.spotify).toBe(brut.playlists['Toutes les recos musicales'].titres.length);
    expect(listeDuGenre(l, 'film')?.oeuvres.length).toBe(sc.listes.film.ajoutees.length);
    expect(listeDuGenre(l, 'film')?.evoquees?.oeuvres.length).toBe(sc.evoquees?.film?.ajoutees?.length);
  });
});

describe('aides', () => {
  const pl = (saison: number | null) => ({
    nom: saison ? `Saison ${saison}` : 'Toutes les recos musicales',
    saison,
    spotify: 's',
    deezer: 'd',
    titres: { spotify: 1, deezer: 1 },
  });
  const listes: Listes = {
    toutes: pl(null),
    saisons: [pl(6), pl(5)],
    senscritique: [{ genre: 'film', url: 'u', oeuvres: [] }],
  };

  it('nombreDeListes compte une playlist une fois pour ses deux plateformes', () => {
    expect(nombreDeListes(listes)).toBe(4);
    expect(nombreDeListes({ ...listes, toutes: null })).toBe(3);
    const avecEvoquees = { ...listes, senscritique: [{ genre: 'film' as const, url: 'u', oeuvres: [], evoquees: { url: 'e', oeuvres: [] } }] };
    expect(nombreDeListes(avecEvoquees)).toBe(5);
  });

  it('playlistDeLaSaison : la saison, sinon celle qui cumule tout', () => {
    expect(playlistDeLaSaison(listes, 5)?.nom).toBe('Saison 5');
    expect(playlistDeLaSaison(listes, undefined)?.nom).toBe('Toutes les recos musicales');
    expect(playlistDeLaSaison(listes, 9)?.nom).toBe('Toutes les recos musicales');
  });

  it('listeDuGenre', () => {
    expect(listeDuGenre(listes, 'film')?.url).toBe('u');
    expect(listeDuGenre(listes, 'bd')).toBeUndefined();
  });
});
