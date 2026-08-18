/**
 * @vitest-environment happy-dom
 *
 * Tests de `src/utils/filtreRecos.ts`.
 *
 * POURQUOI CE FICHIER EXISTE
 * --------------------------
 * Le champ de recherche de `/[source]/recos` ne filtrait rien : son code
 * vivait dans le `<script>` de `SourceCatalog.astro`, un composant que cette
 * page ne monte pas, et Astro n'embarque que les scripts des composants
 * rendus. Le champ existait donc sans écouteur.
 *
 * Aucun test ne pouvait le voir : v8 n'instrumente pas les scripts client des
 * `.astro`. Extraire la logique dans un module la rend enfin vérifiable —
 * c'est la moitié de la correction.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { cablerFiltreRecos } from '../../src/utils/filtreRecos';

function monterGrille() {
  document.body.innerHTML = `
    <input id="search" type="search" />
    <button class="chip is-active" data-filter="all" aria-pressed="true">Tout</button>
    <button class="chip" data-filter="film" aria-pressed="false">Films</button>
    <p id="noresult" aria-live="polite"></p>
    <ul id="reco-grid">
      <li class="card" data-types="film" data-search="pulsions kyan khojandi"></li>
      <li class="card" data-types="serie" data-search="breaking bad"></li>
      <li class="card" data-types="film" data-search="titanic"></li>
    </ul>`;
}

const visibles = () =>
  Array.from(document.querySelectorAll<HTMLElement>('#reco-grid .card'))
    .filter((c) => c.style.display !== 'none').length;

describe('cablerFiltreRecos', () => {
  beforeEach(monterGrille);

  it('câble le filtre quand la grille est présente', () => {
    expect(cablerFiltreRecos()).toBe(true);
  });

  it('ne fait rien, sans lever, quand la grille est absente', () => {
    document.body.innerHTML = '<input id="search" />';
    expect(cablerFiltreRecos()).toBe(false);
  });

  it('filtre sur la saisie — le défaut signalé le 2026-08-18', () => {
    cablerFiltreRecos();
    const search = document.getElementById('search') as HTMLInputElement;
    search.value = 'pulsions';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    expect(visibles()).toBe(1);
  });

  it('tolère les fautes de frappe', () => {
    cablerFiltreRecos();
    const search = document.getElementById('search') as HTMLInputElement;
    search.value = 'titanik';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    expect(visibles()).toBe(1);
  });

  it('filtre sur les puces de type', () => {
    cablerFiltreRecos();
    const chipFilm = document.querySelector<HTMLButtonElement>('[data-filter="film"]')!;
    chipFilm.click();
    expect(visibles()).toBe(2);
    expect(chipFilm.getAttribute('aria-pressed')).toBe('true');
  });

  it('combine le type ET le texte', () => {
    cablerFiltreRecos();
    document.querySelector<HTMLButtonElement>('[data-filter="film"]')!.click();
    const search = document.getElementById('search') as HTMLInputElement;
    search.value = 'titanic';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    expect(visibles()).toBe(1);
  });

  it('revient à tout afficher quand on efface la saisie', () => {
    cablerFiltreRecos();
    const search = document.getElementById('search') as HTMLInputElement;
    search.value = 'pulsions';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    search.value = '';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    expect(visibles()).toBe(3);
  });

  it('annonce quand rien ne correspond', () => {
    cablerFiltreRecos();
    const search = document.getElementById('search') as HTMLInputElement;
    search.value = 'zzzzzzzz';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    expect(visibles()).toBe(0);
    expect(document.getElementById('noresult')!.textContent).toContain('Aucun résultat');
  });

  it('fonctionne sans champ de recherche ni région d’annonce', () => {
    document.body.innerHTML = `
      <ul id="reco-grid"><li class="card" data-types="film" data-search="x"></li></ul>`;
    expect(cablerFiltreRecos()).toBe(true);
  });
});
