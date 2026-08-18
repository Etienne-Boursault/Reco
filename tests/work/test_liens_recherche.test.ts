/**
 * Les liens de diffuseurs mènent à une RECHERCHE, pas à l'œuvre.
 *
 * Relevé du 2026-08-18 : sur les 1632 liens `watchProviders` du corpus, 1601
 * (98 %) sont des URL de recherche — et pour CHAQUE hôte, la proportion est de
 * 100 %. La cause est en amont : TMDB donne le nom des diffuseurs d'une œuvre,
 * jamais leur lien direct, donc `enrich_tmdb.py` fabrique une recherche.
 *
 * Le repli est légitime. Ce qui ne l'était pas, c'est que la page d'œuvre les
 * affichait sous le seul nom du diffuseur : le visiteur lisait « Molotov TV »,
 * cliquait, et tombait sur un formulaire. Ces tests fixent la frontière entre
 * « ce lien mène à l'œuvre » et « ce lien lance une recherche ».
 */
import { describe, expect, it } from 'vitest';
import { estRecherche, workExternalLinks } from '../../src/lib/work/aggregator';

describe('estRecherche', () => {
  // Les douze URL réellement relevées sur /oeuvre/0071568d (« La Pampa »).
  it.each([
    ['https://www.molotov.tv/search?q=La%20Pampa'],
    ['https://www.primevideo.com/-/fr/search/?phrase=La%20Pampa'],
    ['https://www.sooner.fr/recherche?q=La%20Pampa'],
    ['https://www.netflix.com/search?q=La%20Pampa'],
    ['https://tv.apple.com/search?term=La%20Pampa'],
    ['https://www.pathehome.com/recherche?text=La%20Pampa'],
  ])('reconnaît la recherche %s', (url) => {
    expect(estRecherche(url)).toBe(true);
  });

  it.each([
    // Une adresse qui mène VRAIMENT à l'œuvre ne doit pas être marquée.
    ['https://www.themoviedb.org/movie/12345-la-pampa/watch?locale=FR'],
    ['https://www.canalplus.com/series/iris-saison-1-episode-1/h/26903523_50001'],
    ['https://www.youtube.com/watch?v=h6fcK_fRYaI'],
    ['https://www.disneyplus.com/browse/entity-b329134e'],
  ])('laisse passer le lien direct %s', (url) => {
    expect(estRecherche(url)).toBe(false);
  });

  it('reconnaît « /cmd/searchOnsite », que Canal+ utilise 145 fois', () => {
    // Une fin de mot après « search » casserait ce cas : c'est pourquoi la
    // règle porte sur le DÉBUT du segment.
    expect(estRecherche('https://www.canalplus.com/cmd/searchOnsite?query=x')).toBe(true);
  });

  it('reconnaît YouTube, dont le chemin ne dit pas « search »', () => {
    expect(estRecherche('https://www.youtube.com/results?search_query=La+Pampa')).toBe(true);
  });

  it('ne prend pas la catégorie de Google Play pour une recherche', () => {
    // `?c=movies` classe, il n'interroge pas — 81 liens du corpus le portent.
    expect(estRecherche('https://play.google.com/store/movies?c=movies')).toBe(false);
  });

  it('ne lève pas sur une URL illisible', () => {
    expect(estRecherche('pas une url')).toBe(false);
    expect(estRecherche('')).toBe(false);
  });

  it('ignore un paramètre qui ne porte pas de requête', () => {
    expect(estRecherche('https://exemple.fr/film?locale=FR&autoplay=1')).toBe(false);
  });
});

describe('workExternalLinks marque les diffuseurs', () => {
  it('distingue la recherche du lien direct sur le même item', () => {
    const liens = workExternalLinks({
      watchProviders: [
        { name: 'Molotov TV', url: 'https://www.molotov.tv/search?q=La%20Pampa' },
        { name: 'Canal+', url: 'https://www.canalplus.com/series/iris/h/269035' },
      ],
    } as never);
    expect(liens.map((l) => [l.label, l.recherche])).toEqual([
      ['Molotov TV', true],
      ['Canal+', false],
    ]);
  });

  it('ne marque pas les liens curés à la main', () => {
    // `customLinks` est posé par un humain : il mène à l'œuvre par construction.
    const liens = workExternalLinks({
      customLinks: [{ label: 'Site officiel', url: 'https://exemple.fr/x' }],
    } as never);
    expect(liens[0].recherche).toBeUndefined();
  });
});
