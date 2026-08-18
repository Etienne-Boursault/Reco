/**
 * @vitest-environment happy-dom
 *
 * Tests de `src/utils/lienEvitement.ts`.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Le lien « Aller au contenu principal » pointe `#main`. En l'activant, le
 * navigateur inscrit l'ancre dans l'URL : `http://…/#main` reste affiche dans
 * la barre d'adresse, entre dans l'historique, et se retrouve copie-colle par
 * qui partage la page.
 *
 * Releve a la relecture du 2026-08-18. C'est le comportement natif d'un lien
 * d'ancre, et beaucoup de sites le laissent — mais personne ne l'a demande, et
 * il n'apporte rien : l'ancre a rempli son office au moment du saut.
 *
 * On la retire APRES le saut, sans toucher au focus, qui est tout l'interet du
 * lien.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { cablerLienEvitement } from '../../src/utils/lienEvitement';

function monter(): HTMLAnchorElement {
  document.body.innerHTML =
    '<a href="#main" class="skip-link">Aller au contenu</a>' +
    '<main id="main" tabindex="-1"><p>contenu</p></main>';
  return document.querySelector('.skip-link') as HTMLAnchorElement;
}

describe('cablerLienEvitement', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    history.replaceState(null, '', '/une-page');
  });

  it('ne fait rien quand le lien est absent', () => {
    document.body.innerHTML = '<p>rien</p>';
    expect(cablerLienEvitement()).toBe(false);
  });

  it('se cable quand le lien est present', () => {
    monter();
    expect(cablerLienEvitement()).toBe(true);
  });

  it('retire l ancre de l URL apres le saut', () => {
    const lien = monter();
    cablerLienEvitement();
    lien.click();
    expect(location.hash).toBe('');
    expect(location.pathname).toBe('/une-page');
  });

  it('conserve la chaine de requete', () => {
    // Une URL peut porter des parametres qui comptent : les perdre en
    // nettoyant l'ancre serait pire que l'ancre elle-meme.
    history.replaceState(null, '', '/une-page?q=titanic');
    const lien = monter();
    cablerLienEvitement();
    lien.click();
    expect(location.search).toBe('?q=titanic');
    expect(location.hash).toBe('');
  });

  it('donne le focus au contenu', () => {
    // C'est tout l'interet du lien : nettoyer l'URL ne doit pas le lui faire
    // perdre. Le saut natif de happy-dom ne deplace pas le focus, on le pose
    // donc nous-memes — et ce test verifie qu'on le fait.
    const lien = monter();
    cablerLienEvitement();
    lien.click();
    expect(document.activeElement?.id).toBe('main');
  });

  it('n ajoute PAS d entree dans l historique', () => {
    // `replaceState` et non `pushState` : le bouton Retour doit ramener a la
    // page precedente, pas a la meme page avec une ancre.
    const lien = monter();
    cablerLienEvitement();
    const avant = history.length;
    lien.click();
    expect(history.length).toBe(avant);
  });

  it('tolere une cible absente', () => {
    document.body.innerHTML = '<a href="#main" class="skip-link">Aller</a>';
    const lien = document.querySelector('.skip-link') as HTMLAnchorElement;
    cablerLienEvitement();
    expect(() => lien.click()).not.toThrow();
  });

  it('ne se cable pas deux fois', () => {
    monter();
    cablerLienEvitement();
    expect(cablerLienEvitement()).toBe(false);
  });

  it('laisse le navigateur agir si history est indisponible', () => {
    // Contexte restreint : on ne doit pas lever, quitte a garder l'ancre.
    const lien = monter();
    cablerLienEvitement();
    const vrai = history.replaceState;
    // @ts-expect-error - on simule un environnement sans replaceState
    history.replaceState = () => { throw new Error('interdit'); };
    expect(() => lien.click()).not.toThrow();
    history.replaceState = vrai;
  });
});
