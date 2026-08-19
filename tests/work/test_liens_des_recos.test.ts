/**
 * Tests de `liensDesRecommandations` et `tousLesLiens`.
 *
 * CE QUE LA RELECTURE A VU
 * ------------------------
 * « Quand je clique sur une œuvre, j'aimerais aussi voir les liens »
 * (2026-08-19). La fiche de Kaamelott n'en affichait aucun, alors que ses
 * quatre recommandations en portent sept, vérifiés un par un : SOONER,
 * JustWatch, M6+, IMDb, TMDB, AlloCiné, site officiel.
 *
 * La raison est structurelle. Les semaines de vérification des liens ont été
 * menées sur les RECOMMANDATIONS ; la fiche d'œuvre, elle, ne lisait que
 * l'item — qui pour Kaamelott ne connaît qu'un compte Instagram.
 */
import { describe, expect, it } from 'vitest';

import {
  liensDesRecommandations,
  tousLesLiens,
  type WorkExternalLink,
} from '../../src/lib/work/aggregator';

const lien = (url: string, label = 'L', ethics?: string) => ({ url, label, ethics });

describe('liensDesRecommandations', () => {
  it('rassemble les liens de plusieurs recommandations', () => {
    const out = liensDesRecommandations([
      [lien('https://a.fr', 'A')],
      [lien('https://b.fr', 'B')],
    ]);
    expect(out.map((l) => l.url)).toEqual(['https://a.fr', 'https://b.fr']);
  });

  it('ne répète jamais une URL', () => {
    // Les recommandations d'une même œuvre portent souvent les mêmes liens :
    // Kaamelott en a sept, identiques sur ses quatre recommandations.
    const out = liensDesRecommandations([
      [lien('https://a.fr'), lien('https://b.fr')],
      [lien('https://b.fr'), lien('https://a.fr')],
    ]);
    expect(out).toHaveLength(2);
  });

  it('garde l’ordre de première apparition', () => {
    // Cet ordre a été posé à la main : le premier lien est le plus utile.
    const out = liensDesRecommandations([
      [lien('https://sooner.fr'), lien('https://justwatch.com')],
      [lien('https://imdb.com'), lien('https://sooner.fr')],
    ]);
    expect(out.map((l) => l.url)).toEqual([
      'https://sooner.fr', 'https://justwatch.com', 'https://imdb.com',
    ]);
  });

  it('reporte l’éthique quand elle est connue', () => {
    const out = liensDesRecommandations([
      [lien('https://a.fr', 'A', 'indie'), lien('https://b.fr', 'B', 'avoid')],
    ]);
    expect(out.map((l) => l.ethics)).toEqual(['indie', 'avoid']);
  });

  it('retombe sur « neutral » pour une éthique inconnue', () => {
    const out = liensDesRecommandations([[lien('https://a.fr', 'A', 'bizarre')]]);
    expect(out[0].ethics).toBe('neutral');
  });

  it('signale les liens qui mènent à une RECHERCHE', () => {
    // La distinction existe déjà côté carte : un lien de recherche ne mène
    // pas à l'œuvre, et l'interface le dit.
    const out = liensDesRecommandations([
      [lien('https://www.deezer.com/search/Orelsan', 'Deezer')],
    ]);
    expect(out[0].recherche).toBe(true);
  });

  it('écarte ce qui n’est pas une URL http(s) sûre', () => {
    const out = liensDesRecommandations([[
      { url: 'javascript:alert(1)', label: 'X' },
      { url: 'ftp://ailleurs.fr', label: 'Y' },
      lien('https://ok.fr', 'OK'),
    ]]);
    expect(out.map((l) => l.url)).toEqual(['https://ok.fr']);
  });

  it('écarte un lien sans libellé', () => {
    const out = liensDesRecommandations([[
      { url: 'https://a.fr' },
      { url: 'https://b.fr', label: '   ' },
      lien('https://c.fr', 'C'),
    ]]);
    expect(out.map((l) => l.url)).toEqual(['https://c.fr']);
  });

  it('supporte une recommandation sans aucun lien', () => {
    expect(liensDesRecommandations([[], [lien('https://a.fr')], []]))
      .toHaveLength(1);
  });

  it('rend une liste vide quand il n’y a rien', () => {
    expect(liensDesRecommandations([])).toEqual([]);
  });

  it('nettoie les espaces autour du libellé', () => {
    const out = liensDesRecommandations([[lien('https://a.fr', '  SOONER  ')]]);
    expect(out[0].label).toBe('SOONER');
  });
});

describe('tousLesLiens', () => {
  const oeuvre: WorkExternalLink[] = [{ label: 'Fiche', url: 'https://fiche.fr' }];
  const recos: WorkExternalLink[] = [{ label: 'Reco', url: 'https://reco.fr' }];

  it('met les liens de l’œuvre en premier', () => {
    // Ils viennent de `customLinks`, posés à la main sur la fiche.
    expect(tousLesLiens(oeuvre, recos).map((l) => l.url)).toEqual([
      'https://fiche.fr', 'https://reco.fr',
    ]);
  });

  it('déduplique sur l’URL, pas sur le libellé', () => {
    // Deux libellés pour la même adresse restent un doublon — c'est le cas
    // de « TMDB » côté œuvre et « Fiche TMDB » côté recommandation.
    const out = tousLesLiens(
      [{ label: 'TMDB', url: 'https://x.fr' }],
      [{ label: 'Fiche TMDB', url: 'https://x.fr' }],
    );
    expect(out).toHaveLength(1);
    expect(out[0].label).toBe('TMDB');   // celui de l'œuvre l'emporte
  });

  it('fonctionne quand l’œuvre n’a aucun lien', () => {
    // Le cas de Kaamelott : l'item ne porte qu'un Instagram, tout vient des
    // recommandations.
    expect(tousLesLiens([], recos)).toEqual(recos);
  });

  it('fonctionne quand les recommandations n’en ont aucun', () => {
    expect(tousLesLiens(oeuvre, [])).toEqual(oeuvre);
  });

  it('rend une liste vide des deux côtés vides', () => {
    expect(tousLesLiens([], [])).toEqual([]);
  });

  it('efface un lien de RECHERCHE quand un lien direct existe', () => {
    // « Bref » affichait « Disney Plus 🔎 » (recherche héritée de TMDB) ET
    // « Disney+ » (l'adresse exacte, vérifiée à la main). Deux pastilles pour
    // la même plateforme, dont une qui fait moins bien.
    const out = tousLesLiens(
      [{ label: 'Disney Plus', url: 'https://www.disneyplus.com/fr-fr/search?q=Bref',
         recherche: true }],
      [{ label: 'Disney+', url: 'https://www.disneyplus.com/fr-fr/series/bref/2rC' }],
    );
    expect(out.map((l) => l.label)).toEqual(['Disney+']);
  });

  it('garde un lien de recherche SANS équivalent direct', () => {
    // Il est alors la seule piste offerte au visiteur.
    const out = tousLesLiens(
      [{ label: 'TF1+', url: 'https://www.tf1.fr/recherche?q=Bref', recherche: true }],
      [{ label: 'Disney+', url: 'https://www.disneyplus.com/x' }],
    );
    expect(out.map((l) => l.label)).toEqual(['TF1+', 'Disney+']);
  });

  it('reconnaît la plateforme malgré le www.', () => {
    const out = tousLesLiens(
      [{ label: 'Disney Plus', url: 'https://www.disneyplus.com/search?q=x',
         recherche: true }],
      [{ label: 'Disney+', url: 'https://disneyplus.com/series/y' }],
    );
    expect(out).toHaveLength(1);
  });

  it('ne retire jamais deux liens directs de la même plateforme', () => {
    // Une série et son film peuvent légitimement coexister.
    const out = tousLesLiens(
      [{ label: 'Disney+ série', url: 'https://www.disneyplus.com/a' }],
      [{ label: 'Disney+ film', url: 'https://www.disneyplus.com/b' }],
    );
    expect(out).toHaveLength(2);
  });

  it('garde un lien de recherche à URL invalide', () => {
    // Faute d'hôte comparable, on ne peut pas prouver le doublon.
    const out = tousLesLiens(
      [{ label: 'Cassé', url: 'pas-une-url', recherche: true }],
      [{ label: 'Bon', url: 'https://exemple.fr/x' }],
    );
    expect(out).toHaveLength(2);
  });
});
