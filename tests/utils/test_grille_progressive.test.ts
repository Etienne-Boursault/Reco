/**
 * @vitest-environment happy-dom
 *
 * Tests de `src/utils/grilleProgressive.ts`.
 *
 * CE QUE CE MODULE REMPLACE
 * -------------------------
 * `applyGridFilter` parcourait TOUTES les cartes a chaque passe et ecrivait
 * `style.display` sur chacune, y compris celles dont l'etat ne changeait pas.
 * Sur les 1 213 cartes de `/recos`, une passe coutait 125 a 327 ms dans
 * Chrome, et la page pesait 96 000 pixels de haut — le navigateur a gele deux
 * fois pendant les mesures.
 *
 * TROIS CHANGEMENTS, chacun teste ici :
 *
 *   1. L'INDEX est construit une fois. Les `dataset` etaient relus a chaque
 *      passe : `card.dataset.types.split(',')` sur 1 213 cartes, a chaque
 *      frappe.
 *
 *   2. L'ECRITURE EST DIFFERENTIELLE. On ne touche que les cartes dont la
 *      visibilite CHANGE. Passer de « titani » a « titanic » n'en modifie
 *      presque aucune ; l'ancienne version les reecrivait toutes.
 *
 *   3. LE RENDU EST PROGRESSIF. Seules les premieres correspondances sont
 *      affichees ; la suite vient quand on descend. Le DOM reste complet —
 *      c'est ce qui preserve le repli sans JavaScript et l'indexation.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GrilleProgressive } from '../../src/utils/grilleProgressive';

/** Des titres franchement distincts : la recherche tolere les fautes, et des
 *  libelles voisins comme « oeuvre 1 » / « oeuvre 2 » se repondraient tous. */
const TITRES = ['titanic', 'breaking bad', 'pulsions', 'kaamelott', 'fleabag',
                'succession', 'euphoria', 'seinfeld', 'mortel', 'brazil'];

function monter(nb = 10): HTMLElement {
  const cartes = Array.from({ length: nb }, (_, i) => {
    const type = i % 2 === 0 ? 'film' : 'serie';
    const titre = TITRES[i % TITRES.length] + (i >= TITRES.length ? ` ${i}` : '');
    return `<li class="card" data-types="${type}" data-search="${titre}"></li>`;
  }).join('');
  document.body.innerHTML =
    `<p id="noresult" aria-live="polite"></p><ul id="reco-grid">${cartes}</ul>`;
  return document.getElementById('reco-grid') as HTMLElement;
}

const visibles = (grille: HTMLElement) =>
  [...grille.children].filter((c) => (c as HTMLElement).style.display !== 'none').length;

function creer(grille: HTMLElement, options = {}) {
  return new GrilleProgressive({
    grille,
    statut: document.getElementById('noresult'),
    messageVide: 'Aucun résultat.',
    lot: 4,
    ...options,
  });
}

describe('rendu progressif', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('n affiche qu un premier lot', () => {
    const grille = monter(10);
    creer(grille).filtrer({ type: 'all', terme: '' });
    expect(visibles(grille)).toBe(4);
  });

  it('revele le lot suivant a la demande', () => {
    const grille = monter(10);
    const g = creer(grille);
    g.filtrer({ type: 'all', terme: '' });
    g.afficherPlus();
    expect(visibles(grille)).toBe(8);
  });

  it('s arrete quand tout est affiche', () => {
    const grille = monter(10);
    const g = creer(grille);
    g.filtrer({ type: 'all', terme: '' });
    g.afficherPlus(); g.afficherPlus(); g.afficherPlus();
    expect(visibles(grille)).toBe(10);
    expect(g.resteAAfficher()).toBe(0);
  });

  it('garde TOUTES les cartes dans le DOM', () => {
    // C'est ce qui preserve le repli sans JavaScript et l'indexation : les
    // cartes non affichees sont masquees, jamais retirees.
    const grille = monter(10);
    creer(grille).filtrer({ type: 'all', terme: '' });
    expect(grille.children.length).toBe(10);
  });
});

describe('filtrage', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('filtre par type', () => {
    const grille = monter(10);
    const g = creer(grille, { lot: 100 });
    expect(g.filtrer({ type: 'film', terme: '' })).toBe(5);
    expect(visibles(grille)).toBe(5);
  });

  it('filtre par texte', () => {
    const grille = monter(10);
    const g = creer(grille, { lot: 100 });
    expect(g.filtrer({ type: 'all', terme: 'kaamelott' })).toBe(1);
  });

  it('combine le type ET le texte', () => {
    const grille = monter(10);
    const g = creer(grille, { lot: 100 });
    // « kaamelott » est en position 3, donc une serie : le filtre « film »
    // doit l'exclure malgre la correspondance du texte.
    expect(g.filtrer({ type: 'film', terme: 'kaamelott' })).toBe(0);
  });

  it('renvoie le TOTAL correspondant, pas le nombre affiche', () => {
    // Le compteur doit dire « 5 resultats » meme si 4 seulement sont a
    // l'ecran : annoncer le lot tromperait sur l'etendue du corpus.
    const grille = monter(10);
    const g = creer(grille, { lot: 2 });
    expect(g.filtrer({ type: 'film', terme: '' })).toBe(5);
    expect(visibles(grille)).toBe(2);
  });

  it('repart du premier lot a chaque nouveau filtre', () => {
    const grille = monter(10);
    const g = creer(grille);
    g.filtrer({ type: 'all', terme: '' });
    g.afficherPlus();
    g.filtrer({ type: 'all', terme: '' });
    expect(visibles(grille)).toBe(4);
  });
});

describe('ecriture differentielle', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('ne touche PAS les cartes dont l etat ne change pas', () => {
    const grille = monter(10);
    const g = creer(grille, { lot: 100 });
    g.filtrer({ type: 'film', terme: '' });
    // On observe les ecritures de `style` sur la premiere carte, qui reste
    // visible d'un filtre a l'autre.
    const premiere = grille.children[0] as HTMLElement;
    let ecritures = 0;
    const observateur = new MutationObserver((m) => { ecritures += m.length; });
    observateur.observe(premiere, { attributes: true, attributeFilter: ['style'] });
    g.filtrer({ type: 'film', terme: 'titanic' });   // elle correspond encore
    observateur.disconnect();
    expect(ecritures).toBe(0);
  });

  it('touche bien celles qui changent', () => {
    const grille = monter(10);
    const g = creer(grille, { lot: 100 });
    g.filtrer({ type: 'all', terme: '' });
    g.filtrer({ type: 'serie', terme: '' });
    expect((grille.children[0] as HTMLElement).style.display).toBe('none');
  });
});

describe('annonce et robustesse', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('annonce quand rien ne correspond', () => {
    const grille = monter(10);
    creer(grille).filtrer({ type: 'all', terme: 'introuvable-xyz' });
    expect(document.getElementById('noresult')?.textContent).toBe('Aucun résultat.');
  });

  it('efface l annonce des qu un resultat revient', () => {
    const grille = monter(10);
    const g = creer(grille);
    g.filtrer({ type: 'all', terme: 'introuvable-xyz' });
    g.filtrer({ type: 'all', terme: '' });
    expect(document.getElementById('noresult')?.textContent).toBe('');
  });

  it('tolere une carte sans dataset', () => {
    document.body.innerHTML = '<ul id="reco-grid"><li class="card"></li></ul>';
    const grille = document.getElementById('reco-grid') as HTMLElement;
    const g = creer(grille);
    expect(g.filtrer({ type: 'all', terme: '' })).toBe(1);
    expect(g.filtrer({ type: 'film', terme: '' })).toBe(0);
  });

  it('tolere une grille vide', () => {
    document.body.innerHTML = '<ul id="reco-grid"></ul>';
    const grille = document.getElementById('reco-grid') as HTMLElement;
    expect(creer(grille).filtrer({ type: 'all', terme: '' })).toBe(0);
  });

  it('tolere l absence de region d annonce', () => {
    document.body.innerHTML = '<ul id="reco-grid"><li class="card"></li></ul>';
    const grille = document.getElementById('reco-grid') as HTMLElement;
    const g = new GrilleProgressive({ grille, messageVide: 'rien', lot: 4 });
    expect(() => g.filtrer({ type: 'film', terme: '' })).not.toThrow();
  });

  it('tolere les fautes de frappe, comme l ancien filtre', () => {
    document.body.innerHTML =
      '<ul id="reco-grid"><li class="card" data-types="film" data-search="titanic"></li></ul>';
    const grille = document.getElementById('reco-grid') as HTMLElement;
    expect(creer(grille).filtrer({ type: 'all', terme: 'titanik' })).toBe(1);
  });
});

describe('reveal au defilement', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('expose une sentinelle a observer', () => {
    const grille = monter(10);
    const g = creer(grille);
    g.filtrer({ type: 'all', terme: '' });
    // La sentinelle est la derniere carte AFFICHEE : quand elle entre dans le
    // champ, il est temps de reveler la suite.
    expect(g.sentinelle()).toBe(grille.children[3]);
  });

  it('ne renvoie pas de sentinelle quand tout est affiche', () => {
    const grille = monter(3);
    const g = creer(grille);
    g.filtrer({ type: 'all', terme: '' });
    expect(g.sentinelle()).toBeNull();
  });
});

describe('lot par defaut', () => {
  beforeEach(() => { document.body.innerHTML = ''; });

  it('utilise un lot par defaut quand on n en donne pas', () => {
    // Assez pour remplir plusieurs ecrans sans en calculer mille : les
    // appelants n'ont pas a le choisir.
    const grille = monter(10);
    const g = new GrilleProgressive({ grille, messageVide: 'rien' });
    g.filtrer({ type: 'all', terme: '' });
    expect(visibles(grille)).toBe(10);   // 10 < lot par defaut
    expect(g.resteAAfficher()).toBe(0);
  });
});
