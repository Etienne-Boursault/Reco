/**
 * barreFiltres.ts — la barre de filtres s'efface quand on parcourt les recos.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * La barre de filtres est `position: sticky` : elle reste à l'écran pendant
 * qu'on parcourt la liste. Sur un large écran c'est confortable, elle prend
 * une bande fine. Sur mobile, le champ de recherche et les seize puces de type
 * s'empilent sur quatre lignes et occupent près de la moitié de la hauteur :
 * il ne reste presque rien pour lire les cartes.
 *
 * Signalé à la relecture du 2026-08-18 : « si je scroll, il faut que les
 * éléments de filtrage disparaissent ».
 *
 * On la masque donc en DESCENDANT et on la rend en REMONTANT. Le choix n'est
 * pas arbitraire : remonter est le geste de quelqu'un qui revient aux
 * commandes, descendre celui de quelqu'un qui lit. La barre suit l'intention
 * plutôt qu'une position absolue dans la page.
 *
 * Il vit dans `utils/` et non dans un `<script>` d'`.astro` pour la raison
 * déjà rencontrée avec `filtreRecos` : Astro n'embarque que les scripts des
 * composants réellement rendus, et un script inline n'est pas mesurable par
 * les tests.
 */

/** En deçà, on est encore en haut de page : rien à escamoter. */
const SEUIL_HAUT = 120;

/** Un mouvement plus petit est du bruit : rebond tactile, défilement par
 *  à-coups. Sans ce seuil, la barre clignoterait. */
const SEUIL_MOUVEMENT = 8;

/**
 * Câble le masquage au défilement sur la barre présente dans le document.
 *
 * Renvoie `false` si la barre est absente — c'est le cas sur l'accueil tant
 * que l'onglet « Toutes les recos » n'a pas été ouvert — ou si elle est déjà
 * câblée. L'appelant peut donc relancer la fonction après une injection de
 * fragment sans empiler les écouteurs.
 */
export function cablerBarreFiltres(): boolean {
  const barre = document.querySelector<HTMLElement>('.toolbar');
  if (!barre || barre.dataset.defilementCable === '1') return false;
  barre.dataset.defilementCable = '1';

  let precedent = window.scrollY;

  const surDefilement = (): void => {
    const actuel = window.scrollY;
    const delta = actuel - precedent;
    if (Math.abs(delta) < SEUIL_MOUVEMENT) return;
    precedent = actuel;

    // Le focus dans la barre l'emporte sur tout le reste : on tape dans le
    // champ, le clavier virtuel s'ouvre et la page défile toute seule —
    // masquer la barre escamoterait la saisie en cours.
    if (barre.contains(document.activeElement)) {
      barre.classList.remove('toolbar--masquee');
      return;
    }

    const masquer = delta > 0 && actuel > SEUIL_HAUT;
    barre.classList.toggle('toolbar--masquee', masquer);
  };

  window.addEventListener('scroll', surDefilement, { passive: true });
  return true;
}
