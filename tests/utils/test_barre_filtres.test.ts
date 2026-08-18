/**
 * @vitest-environment happy-dom
 *
 * Tests de `src/utils/barreFiltres.ts`.
 *
 * CE QUE CE MODULE RESOUT
 * -----------------------
 * La barre de filtres est `position: sticky` : elle reste a l'ecran pendant
 * qu'on parcourt les recos. Sur un large ecran c'est confortable — elle prend
 * une bande fine. Sur mobile, le champ de recherche et les seize puces de
 * type s'empilent sur quatre lignes et occupent pres de la moitie de la
 * hauteur : il ne reste presque rien pour lire les cartes.
 *
 * Signale a la relecture du 2026-08-18 : « si je scroll, il faut que les
 * elements de filtrage disparaissent ».
 *
 * On la masque donc en DESCENDANT et on la rend en REMONTANT. Remonter est le
 * geste de quelqu'un qui cherche a revenir aux commandes ; descendre est le
 * geste de quelqu'un qui lit.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { cablerBarreFiltres } from '../../src/utils/barreFiltres';

function poserBarre(): HTMLElement {
  document.body.innerHTML = '<div class="toolbar"></div><div style="height:5000px"></div>';
  return document.querySelector('.toolbar') as HTMLElement;
}

function defiler(y: number): void {
  Object.defineProperty(window, 'scrollY', { value: y, writable: true, configurable: true });
  window.dispatchEvent(new Event('scroll'));
}

describe('cablerBarreFiltres', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    Object.defineProperty(window, 'scrollY', { value: 0, writable: true, configurable: true });
  });

  it('ne fait rien quand la barre est absente', () => {
    document.body.innerHTML = '<p>rien</p>';
    expect(cablerBarreFiltres()).toBe(false);
  });

  it('se cable quand la barre est presente', () => {
    poserBarre();
    expect(cablerBarreFiltres()).toBe(true);
  });

  it('masque la barre quand on descend', () => {
    const barre = poserBarre();
    cablerBarreFiltres();
    defiler(400);
    expect(barre.classList.contains('toolbar--masquee')).toBe(true);
  });

  it('la rend des qu on remonte', () => {
    const barre = poserBarre();
    cablerBarreFiltres();
    defiler(400);
    defiler(300);
    expect(barre.classList.contains('toolbar--masquee')).toBe(false);
  });

  it('ne masque pas pres du haut de page', () => {
    // Sinon la barre disparaitrait au premier petit mouvement, alors qu'elle
    // est encore a l'ecran et qu'on n'a rien parcouru.
    const barre = poserBarre();
    cablerBarreFiltres();
    defiler(60);
    expect(barre.classList.contains('toolbar--masquee')).toBe(false);
  });

  it('ignore les micro-mouvements', () => {
    // Un defilement par a-coups, ou le rebond d'un ecran tactile, ferait
    // clignoter la barre a chaque pixel.
    const barre = poserBarre();
    cablerBarreFiltres();
    defiler(400);
    defiler(396);
    expect(barre.classList.contains('toolbar--masquee')).toBe(true);
  });

  it('rend la barre quand on revient tout en haut', () => {
    const barre = poserBarre();
    cablerBarreFiltres();
    defiler(400);
    defiler(0);
    expect(barre.classList.contains('toolbar--masquee')).toBe(false);
  });

  it('ne se cable pas deux fois sur la meme barre', () => {
    // `cablerFiltreRecos` est relance apres l'injection du fragment sur
    // l'accueil : sans garde, chaque appel ajouterait un ecouteur de plus.
    const barre = poserBarre();
    cablerBarreFiltres();
    expect(cablerBarreFiltres()).toBe(false);
    expect(barre.dataset.defilementCable).toBe('1');
  });

  it('ne masque jamais la barre quand le focus est dedans', () => {
    // On tape dans le champ de recherche, le clavier virtuel s'ouvre et la
    // page defile : masquer la barre escamoterait le champ en cours de
    // saisie.
    const barre = poserBarre();
    barre.innerHTML = '<input id="search">';
    cablerBarreFiltres();
    (barre.querySelector('input') as HTMLInputElement).focus();
    defiler(400);
    expect(barre.classList.contains('toolbar--masquee')).toBe(false);
  });
});
