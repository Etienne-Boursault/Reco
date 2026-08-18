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
import { GrilleProgressive } from './grilleProgressive';

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

  const grille = new GrilleProgressive({
    grille: grid,
    statut: noresult,
    messageVide: 'Aucun résultat.',
  });

  let activeType = 'all';
  let term = '';

  // Révélation au défilement : quand la dernière carte affichée entre dans le
  // champ, on découvre le lot suivant. Un `IntersectionObserver` plutôt qu'un
  // écouteur de `scroll` — il ne réveille le fil principal que lorsque la
  // sentinelle bouge vraiment.
  //
  // Le repli est silencieux : sans `IntersectionObserver`, on affiche tout
  // d'un coup. Un visiteur sur un navigateur ancien retrouve exactement la
  // page d'avant cette refonte, en moins rapide — jamais une page tronquée.
  const guetteur =
    typeof IntersectionObserver === 'undefined'
      ? null
      : new IntersectionObserver((entrees) => {
          if (!entrees.some((e) => e.isIntersecting)) return;
          if (grille.afficherPlus() > 0) surveiller();
        }, {
          // 1 200 px, soit environ quatre rangées de cartes : la suite est
          // prête avant qu'on atteigne le bas. Mesuré à 600 px, la révélation
          // se déclenchait au moment même où l'on arrivait sur la dernière
          // rangée — techniquement juste, visiblement tardif.
          rootMargin: '1200px',
        });

  function surveiller() {
    if (!guetteur) return;
    guetteur.disconnect();
    const sentinelle = grille.sentinelle();
    if (sentinelle) guetteur.observe(sentinelle);
  }

  function apply() {
    grille.filtrer({ type: activeType, terme: term });
    if (guetteur) {
      surveiller();
    } else {
      // Sans guetteur, rien ne révélerait la suite : on déplie tout.
      while (grille.afficherPlus() > 0) { /* jusqu'au bout */ }
    }
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

  // La saisie est TEMPORISÉE, le clic ne l'est pas.
  //
  // Filtrer à chaque touche rendait la saisie poussive : sur les 1 213 cartes
  // du corpus, une passe coûtait 125 à 327 ms dans Chrome. 120 ms est en
  // dessous du seuil où une interface paraît ne pas répondre, et au-dessus de
  // l'intervalle entre deux touches d'une frappe courante.
  //
  // Un clic sur une puce est un geste délibéré : le temporiser donnerait
  // l'impression que le bouton n'a pas répondu.
  let attente: ReturnType<typeof setTimeout> | undefined;
  search?.addEventListener('input', () => {
    term = search.value;
    clearTimeout(attente);
    attente = setTimeout(apply, 120);
  });

  // Premier affichage : la grille arrive entièrement visible dans le HTML
  // (c'est ce que voit un visiteur sans JavaScript), on la ramène au premier
  // lot.
  apply();

  return true;
}
