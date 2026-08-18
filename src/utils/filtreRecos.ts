/**
 * filtreRecos.ts — le filtrage d'une grille de recos, par type et par texte.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Cette logique vivait dans le `<script>` de `SourceCatalog.astro`, alors que
 * l'interface qu'elle pilote — le champ `#search`, les puces `.chip`, la
 * grille `#reco-grid` — est rendue AUSSI par `AllRecosView.astro`.
 *
 * Astro n'embarque que les scripts des composants RÉELLEMENT rendus. Sur
 * `/[source]/recos`, qui monte `AllRecosView` sans `SourceCatalog`, le champ
 * de recherche et les puces existaient donc sans le moindre écouteur : on
 * pouvait taper, rien ne se passait. Signalé le 2026-08-18.
 *
 * C'est exactement le défaut qui avait déjà cassé les styles des cartes le
 * 2026-08-17, pour la même raison : une dépendance portée par un composant
 * absent de la page. Un module partagé, importé par les deux, le referme.
 *
 * Il est aussi TESTABLE, ce qu'un script inline d'`.astro` n'est pas : v8
 * n'instrumente pas ces scripts, et cette logique échappait à toute mesure.
 */
import { applyGridFilter } from './gridFilter';
import { fuzzyMatch } from './search';

/**
 * Câble le filtre sur la grille présente dans le document.
 *
 * Ne fait RIEN si la grille est absente : sur la page d'accueil, elle n'arrive
 * qu'au premier clic sur l'onglet « Toutes les recos ». C'est pourquoi
 * l'appelant peut relancer la fonction après une injection de fragment.
 *
 * @returns `true` si le filtre a été câblé, `false` s'il n'y avait pas de
 *          grille — de quoi vérifier le câblage dans un test.
 */
export function cablerFiltreRecos(): boolean {
  const grid = document.getElementById('reco-grid');
  if (!grid) return false;

  const search = document.getElementById('search') as HTMLInputElement | null;
  const chips = Array.from(document.querySelectorAll<HTMLButtonElement>('.chip'));
  const noresult = document.getElementById('noresult');

  let activeType = 'all';
  let term = '';

  function apply() {
    applyGridFilter({
      grid: grid as HTMLElement,
      status: noresult,
      emptyMessage: 'Aucun résultat.',
      matches: (card) => {
        const okType =
          activeType === 'all' ||
          (card.dataset.types?.split(',').includes(activeType) ?? false);
        const okText = !term || fuzzyMatch(term, card.dataset.search ?? '');
        return okType && okText;
      },
    });
  }

  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      activeType = chip.dataset.filter ?? 'all';
      chips.forEach((c) => {
        const on = c === chip;
        c.classList.toggle('is-active', on);
        c.setAttribute('aria-pressed', String(on));
      });
      apply();
    });
  });

  search?.addEventListener('input', () => {
    term = search.value;
    apply();
  });

  return true;
}
