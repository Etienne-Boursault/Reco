/**
 * La page « où regarder » de TMDB ne doit pas porter le logo de la FICHE
 * TMDB : les deux vivent sur le même hôte, et 269 cartes affichaient deux
 * pictogrammes identiques côte à côte — lus comme un doublon (retour
 * utilisateur, image #22).
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeEach, describe, expect, it } from 'vitest';
import RecoCard from '../../src/components/RecoCard.astro';

let container: AstroContainer;
beforeEach(async () => {
  container = await AstroContainer.create();
});

const rendre = (links: unknown[]) =>
  container.renderToString(RecoCard, {
    props: {
      reco: { id: 'ubm-1', title: 'T', types: ['film'], links },
      sourceId: 'un-bon-moment',
    },
  });

const lien = (label: string, url: string, kind = 'streaming') => ({
  label, url, kind, ethics: 'neutral',
});

describe('RecoCard — icône de la page « où regarder »', () => {
  it('la fiche TMDB garde son logo', async () => {
    const html = await rendre([lien('TMDB', 'https://www.themoviedb.org/movie/597', 'info')]);
    expect(html).toContain('www.themoviedb.org.svg');
  });

  it('la page de visionnage TMDB ne le porte PAS', async () => {
    const html = await rendre([
      lien('Où regarder', 'https://www.themoviedb.org/movie/597-titanic/watch?locale=FR'),
    ]);
    expect(html).not.toContain('www.themoviedb.org.svg');
  });

  it('les deux ensemble ne montrent qu’UN seul logo TMDB', async () => {
    const html = await rendre([
      lien('TMDB', 'https://www.themoviedb.org/movie/597', 'info'),
      lien('Où regarder', 'https://www.themoviedb.org/movie/597-titanic/watch?locale=FR'),
    ]);
    expect(html.match(/www\.themoviedb\.org\.svg/g)?.length ?? 0).toBe(1);
  });

  it('une vidéo YouTube garde son logo malgré son chemin /watch', async () => {
    // Sans cette garde, chaque vidéo du corpus perdrait son pictogramme.
    const html = await rendre([lien('YouTube', 'https://www.youtube.com/watch?v=abc')]);
    expect(html).toContain('www.youtube.com.svg');
  });
});
