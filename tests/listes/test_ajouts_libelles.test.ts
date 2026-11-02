/**
 * Derniers ajouts (`src/lib/listes/ajouts.ts`) et phrases (`libelles.ts`).
 *
 * La règle musicale doit rester celle de `tools/playlists_musique.py` :
 * mention validée, pas une citation, type musique/album/artiste, humoriste
 * non exclu, lien Spotify.
 */
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import {
  EXCLUS_MUSIQUE,
  derniersAjouts,
  episodeAMusique,
  mentionsMusicales,
  plusRecentesParFiche,
  premieresDeLaListe,
  type MentionAjout,
} from '../../src/lib/listes/ajouts';
import {
  apercuSensCritique,
  ariaEcouter,
  ariaVoirListe,
  descriptionListes,
  libelleOeuvres,
  libelleTitres,
  nomGenre,
  phraseBandeau,
  saisonCourte,
} from '../../src/lib/listes/libelles';
import type { Playlist } from '../../src/lib/listes/donnees';

const SPOTIFY = [{ url: 'https://open.spotify.com/artist/x' }];
const item = (id: string, types: string[], extra: Record<string, unknown> = {}) => ({ id, title: id.toUpperCase(), types, ...extra });
const mention = (id: string, itemId: string, ep: string | null, extra: Partial<MentionAjout> = {}): MentionAjout => ({
  id,
  itemId,
  status: 'validated',
  kind: 'reco',
  sourceRef: { episodeGuid: ep },
  ...extra,
});
const ep = (guid: string, jour: string, season?: number, number?: number) => ({ guid, date: new Date(jour), season, number });

describe('mentionsMusicales', () => {
  const items = new Map([
    ['mus', item('mus', ['musique'])],
    ['film', item('film', ['film'])],
    ['fiche', item('fiche', ['artiste'], { externalIds: { spotify: 'abc' } })],
    ['perso', item('perso', ['album'], { customLinks: [{ url: 'https://open.spotify.com/album/1' }] })],
    ['nu', item('nu', ['album'], { externalIds: null, customLinks: null })],
    ['162d3378', item('162d3378', ['artiste'])],
  ]);
  const recos = new Map([
    ['m1', { links: SPOTIFY }],
    ['m2', { links: SPOTIFY }],
    ['m3', { links: SPOTIFY }],
    ['m4', { links: SPOTIFY }],
    ['m5', { links: SPOTIFY }],
    ['m6', { links: SPOTIFY }],
  ]);

  it('applique chaque condition de la règle des playlists', () => {
    const r = mentionsMusicales(
      items,
      [
        mention('m1', 'mus', 'e'),
        mention('m2', 'film', 'e'),
        mention('m3', 'mus', 'e', { kind: 'citation' }),
        mention('m4', 'mus', 'e', { status: 'draft' }),
        mention('m5', '162d3378', 'e'),
        mention('m6', 'absent', 'e'),
        mention('m7', 'mus', 'e'),
        mention('m8', 'fiche', 'e'),
        mention('m9', 'perso', 'e'),
        mention('m10', 'nu', 'e'),
      ],
      recos,
    );
    expect(r.map((m) => m.id)).toEqual(['m1', 'm8', 'm9']);
  });

  it('les humoristes exclus sont ceux du script Python', () => {
    const script = readFileSync('tools/playlists_musique.py', 'utf-8');
    const exclus = script.match(/^EXCLUS = \{([^}]*)\}/m)?.[1].match(/"[^"]+"/g)?.map((s) => s.slice(1, -1));
    expect(new Set(exclus)).toEqual(EXCLUS_MUSIQUE);
  });
});

describe('plusRecentesParFiche et premieresDeLaListe', () => {
  const episodes = new Map([
    ['vieux', ep('vieux', '2024-01-01', 4, 1)],
    ['neuf', ep('neuf', '2026-10-30', 6, 7)],
    ['sansdate', { guid: 'sansdate' }],
  ]);
  const titres = new Map([
    ['a', 'Alpha'],
    ['b', 'Bravo'],
  ]);

  it('garde l’épisode le plus récent de chaque fiche, trie par date puis titre inversé', () => {
    const r = plusRecentesParFiche(
      [
        mention('1', 'a', 'vieux'),
        mention('2', 'a', 'neuf'),
        mention('3', 'a', 'vieux'),
        mention('4', 'b', 'neuf'),
        mention('5', 'c', null),
        mention('6', 'd', 'sansdate'),
        mention('7', 'b', 'neuf'),
        mention('8', 'e', 'inconnu'),
      ],
      episodes,
      titres,
    );
    expect(r).toEqual([
      { itemId: 'b', episodeGuid: 'neuf' },
      { itemId: 'a', episodeGuid: 'neuf' },
      { itemId: 'c', episodeGuid: null },
      { itemId: 'd', episodeGuid: 'sansdate' },
      { itemId: 'e', episodeGuid: 'inconnu' },
    ]);
  });

  it('à date et titre égaux, l’ordre est stable', () => {
    const r = plusRecentesParFiche([mention('1', 'x', 'neuf'), mention('2', 'y', 'neuf')], episodes, new Map());
    expect(r.map((a) => a.itemId)).toEqual(['x', 'y']);
  });

  it('premieresDeLaListe saute les fiches sans page et s’arrête au nombre voulu', () => {
    const recentes = new Map([
      ['a', { itemId: 'a', episodeGuid: 'neuf' }],
      ['b', { itemId: 'b', episodeGuid: null }],
      ['c', { itemId: 'c', episodeGuid: null }],
    ]);
    expect(premieresDeLaListe(['z', 'a', 'b', 'c'], recentes, 2).map((a) => a.itemId)).toEqual(['a', 'b']);
  });
});

describe('derniersAjouts et episodeAMusique', () => {
  const corpus = {
    items: [item('mus', ['musique']), item('film1', ['film']), item('film2', ['film'])],
    mentions: [
      mention('r1', 'mus', 'neuf'),
      mention('r2', 'film1', 'vieux'),
      mention('r3', 'film2', 'neuf', { status: 'discarded' }),
      mention('r4', 'fantome', 'neuf', { status: 'validated' }),
    ],
    recos: new Map([['r1', { links: SPOTIFY }]]),
    episodes: [ep('vieux', '2024-01-01'), ep('neuf', '2026-10-30', 6, 7)],
  };

  it('musique et listes, avec le badge de l’épisode', () => {
    const r = derniersAjouts(corpus, [{ genre: 'film', oeuvres: ['film2', 'film1', 'fantome'] }], { musique: 4, liste: 3 });
    expect(r.musique).toEqual([{ item: corpus.items[0], detail: 'S6·E7' }]);
    // film2 n'a qu'une mention écartée, fantome n'a pas de fiche : pas de page.
    expect(r.listes.get('film')).toEqual([{ item: corpus.items[1], detail: '' }]);
  });

  it('une mention sans épisode donne un badge vide', () => {
    const r = derniersAjouts({ ...corpus, mentions: [mention('r1', 'mus', null)] }, [], { musique: 1, liste: 1 });
    expect(r.musique[0].detail).toBe('');
  });

  it('episodeAMusique ne regarde que l’épisode demandé', () => {
    expect(episodeAMusique(corpus, 'neuf')).toBe(true);
    expect(episodeAMusique(corpus, 'vieux')).toBe(false);
  });
});

describe('libellés', () => {
  const pl = (spotify: number, deezer: number, saison: number | null = 6): Playlist => ({
    nom: saison ? `Saison ${saison}` : 'Toutes les recos musicales',
    saison,
    spotify: 's',
    deezer: 'd',
    titres: { spotify, deezer },
  });

  it('titres : accord, et les deux nombres s’ils divergent', () => {
    expect(libelleTitres(pl(298, 298))).toBe('298 titres');
    expect(libelleTitres(pl(1, 1))).toBe('1 titre');
    expect(libelleTitres(pl(18, 17))).toBe('18 titres sur Spotify, 17 sur Deezer');
    expect(libelleOeuvres(1)).toBe('1 œuvre');
    expect(libelleOeuvres(122)).toBe('122 œuvres');
  });

  it('noms et noms accessibles', () => {
    expect(nomGenre('bd')).toBe('Bandes dessinées');
    expect(saisonCourte(pl(1, 1, 6))).toBe('S6');
    expect(ariaEcouter(pl(1, 1), 'Spotify')).toBe('Écouter la playlist « Saison 6 » sur Spotify (nouvel onglet)');
    expect(ariaVoirListe('serie')).toBe('Voir la liste SensCritique des séries (nouvel onglet)');
  });

  it('aperçu SensCritique de la carte d’accueil', () => {
    const l = (genre: 'film' | 'serie' | 'livre' | 'bd') => ({ genre, url: 'u', oeuvres: [] });
    expect(apercuSensCritique([l('film'), l('serie'), l('livre'), l('bd')])).toBe('Films, séries, livres et BD sur SensCritique');
    expect(apercuSensCritique([l('bd')])).toBe('BD sur SensCritique');
  });

  it('méta-description', () => {
    const sc = [{ genre: 'film' as const, url: 'u', oeuvres: ['a'] }];
    expect(descriptionListes('UBM', { toutes: pl(298, 298, null), saisons: [pl(1, 1), pl(2, 2, 5)], senscritique: sc })).toBe(
      'Les recos du podcast UBM en playlists Spotify et Deezer et en listes SensCritique : 298 titres dans « Toutes les recos musicales », 2 playlists de saison, 1 liste SensCritique.',
    );
    expect(descriptionListes('UBM', { toutes: null, saisons: [], senscritique: sc })).toBe(
      'Les recos du podcast UBM en playlists Spotify et Deezer et en listes SensCritique : 1 liste SensCritique.',
    );
  });

  it('phrase du bandeau : une liste, ou livres et BD ensemble', () => {
    const l = (genre: 'film' | 'serie' | 'livre' | 'bd', n: number) => ({ genre, url: 'u', oeuvres: Array(n).fill('x') });
    expect(phraseBandeau([l('film', 122)])).toBe('Une liste à suivre sur SensCritique rassemble 122 des films recommandés ici.');
    expect(phraseBandeau([l('livre', 51), l('bd', 14)])).toBe(
      'Deux listes à suivre sur SensCritique rassemblent 51 des livres et 14 des BD recommandés ici.',
    );
    expect(phraseBandeau([l('bd', 3)])).toBe('Une liste à suivre sur SensCritique rassemble 3 des BD recommandées ici.');
  });
});
