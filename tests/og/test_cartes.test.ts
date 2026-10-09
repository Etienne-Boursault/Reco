/**
 * tests/og/test_cartes.test.ts
 *
 * `src/lib/og/cartes.ts` — quelles cartes de partage le build produit, et
 * avec quels chiffres (cartes « Étiquette », audit d'interface du 2026-10-07).
 * Module pur : pas de mock d'Astro, les collections sont passées à plat.
 */
import { describe, expect, it } from 'vitest';

import {
  cartesDuSite,
  libelleStatsOeuvre,
  oeuvreAUneCarte,
  type DonneesCartes,
} from '../../src/lib/og/cartes';

const SOURCE = { id: 'ubm', title: 'Un Bon Moment', tagline: 'Le podcast', accent: '#ff0066', bg: '#101010' };

const reco = (id: string, over: Partial<DonneesCartes['recos'][number]> = {}) => ({
  id, sourceId: 'ubm', episodeGuid: 'ep-1', status: 'validated', title: id, ...over,
});
const mention = (id: string, itemId: string, over: Record<string, unknown> = {}) => ({
  id, itemId, kind: 'reco' as const, status: 'validated' as const,
  sourceRef: { sourceId: 'ubm', episodeGuid: 'ep-1' }, ...over,
});

function donnees(over: Partial<DonneesCartes> = {}): DonneesCartes {
  return {
    sources: [SOURCE],
    episodes: [{ guid: 'ep-1', sourceId: 'ubm', title: 'Babor et Jenny (Un Bon Moment, S6-E03)', number: 3, season: 6 }],
    recos: [],
    items: [],
    mentions: [],
    ...over,
  };
}

const carte = (d: DonneesCartes, slug: string) => cartesDuSite(d).find((c) => c.slug === slug)?.carte;

describe('cartesDuSite — accueil et source', () => {
  it('produit toujours la carte de repli, même sans contenu', () => {
    const c = cartesDuSite({ sources: [], episodes: [], recos: [], items: [], mentions: [] });
    expect(c.map((x) => x.slug)).toEqual(['default']);
    expect(c[0]!.carte.chiffre).toBe(0);
  });

  it('la source compte ses vraies recommandations et ses épisodes', () => {
    const d = donnees({
      recos: [reco('a'), reco('b'), reco('c', { kind: 'citation' }), reco('d', { status: 'discarded' })],
    });
    const c = carte(d, 'ubm')!;
    expect(c.chiffre).toBe(2);
    expect(c.chiffreLibelle).toBe('recommandations');
    expect(c.chiffreContexte).toBe('dans 1 épisode');
    expect(c.rubrique).toBe('Podcast · Un Bon Moment');
    expect(c.accent).toBe('#ff0066');
  });

  it('en mono-source, la carte de la source porte le nom du SITE (c’est l’accueil)', () => {
    expect(carte(donnees(), 'ubm')!.titre).toBe('Une Bonne Reco');
  });

  it('en multi-source, chaque source garde son titre', () => {
    const d = donnees({ sources: [SOURCE, { id: 'autre', title: 'Autre podcast' }] });
    expect(carte(d, 'autre')!.titre).toBe('Autre podcast');
  });
});

describe('cartesDuSite — épisodes', () => {
  it('une carte par épisode recommandant, avec repère, compte et trois titres', () => {
    const d = donnees({
      recos: [
        reco('Métal Hurlant', { timestamp: '00:05:00' }),
        reco('Pause', { timestamp: '00:20:00' }),
        reco('Les Pieds sur Terre', { timestamp: '00:10:00' }),
        reco('Irréalisable', { guestWork: true, timestamp: '00:01:00' }),
        reco('Évoquée', { kind: 'citation' }),
      ],
    });
    const c = carte(d, 'ubm/episode/ep-1')!;
    expect(c.repere).toBe('S6·E3');
    expect(c.chiffre).toBe(4);
    expect(c.chiffreContexte).toBe('et 1 œuvre évoquée');
    // Le suffixe « (Un Bon Moment, S6-E03) » répète le repère : retiré.
    expect(c.titre).toBe('Babor et Jenny');
    // Spontanées d'abord, dans l'ordre où l'épisode les cite.
    expect(c.liste).toEqual(['Métal Hurlant', 'Les Pieds sur Terre', 'Pause']);
  });

  it('pas de carte pour un épisode sans recommandation, ou qui n’a que des citations', () => {
    const d = donnees({ recos: [reco('x', { kind: 'citation' })] });
    expect(carte(d, 'ubm/episode/ep-1')).toBeUndefined();
  });

  it('une reco d’une autre source ne donne pas de carte à un guid identique', () => {
    const d = donnees({ recos: [reco('x', { sourceId: 'autre' })] });
    expect(carte(d, 'ubm/episode/ep-1')).toBeUndefined();
  });
});

describe('cartesDuSite — galeries et œuvres', () => {
  const items = [
    { id: 'f1', sourceId: 'ubm', title: 'Bref', types: ['serie'], creator: 'Kyan Khojandi' },
    { id: 'f2', sourceId: 'ubm', title: 'Kaamelott', types: ['film', 'serie'], creator: 'Alexandre Astier' },
  ];

  it('une carte par galerie non vide, avec le nombre de sa page', () => {
    const d = donnees({ items, mentions: [mention('m1', 'f1'), mention('m2', 'f2')] });
    const series = carte(d, 'ubm/galerie/series')!;
    expect(series.chiffre).toBe(2);
    expect(series.chiffreLibelle).toBe('séries recommandées');
    expect(series.titre).toBe('Toutes les séries');
    expect(carte(d, 'ubm/galerie/films')!.chiffreLibelle).toBe('film recommandé');
    expect(carte(d, 'ubm/galerie/livres')).toBeUndefined();
  });

  it('une œuvre citée deux fois a sa carte, avec le libellé de sa fiche', () => {
    const d = donnees({
      items,
      mentions: [mention('m1', 'f1'), mention('m2', 'f1', { kind: 'citation' }), mention('m3', 'f2')],
    });
    const bref = carte(d, 'ubm/oeuvre/f1')!;
    expect(bref.chiffre).toBe(2);
    expect(bref.chiffreLibelle).toBe('mentions');
    expect(bref.sousTitre).toBe('Kyan Khojandi');
    expect(bref.detail).toBe('Recommandée 1 fois · évoquée 1 fois');
    expect(bref.rubrique).toBe('Série');
    // Citée une seule fois : sa carte aussi (une carte par fiche, 2026-10-07),
    // avec le singulier.
    const unique = carte(d, 'ubm/oeuvre/f2')!;
    expect(unique.chiffre).toBe(1);
    expect(unique.chiffreLibelle).toBe('mention');
  });

  it('une mention écartée ne compte pas', () => {
    const d = donnees({ items, mentions: [mention('m1', 'f1'), mention('m2', 'f1', { status: 'discarded' })] });
    expect(carte(d, 'ubm/oeuvre/f1')!.chiffre).toBe(1);
    // Sans aucune mention publique, pas de fiche, donc pas de carte.
    const vide = donnees({ items, mentions: [mention('m2', 'f1', { status: 'discarded' })] });
    expect(carte(vide, 'ubm/oeuvre/f1')).toBeUndefined();
  });
});

describe('aides', () => {
  it('oeuvreAUneCarte : dès la première mention, toute fiche a sa carte', () => {
    expect(oeuvreAUneCarte(0)).toBe(false);
    expect(oeuvreAUneCarte(1)).toBe(true);
    expect(oeuvreAUneCarte(2)).toBe(true);
  });

  it('libelleStatsOeuvre reprend les tournures de la fiche œuvre', () => {
    expect(libelleStatsOeuvre(5, 14)).toBe('Recommandée 5 fois · évoquée 9 fois');
    expect(libelleStatsOeuvre(1, 1)).toBe('Recommandée 1 fois');
    expect(libelleStatsOeuvre(0, 3)).toBe('Évoquée 3 fois');
  });
});
