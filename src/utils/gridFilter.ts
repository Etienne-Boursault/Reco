/**
 * Filtrage client d'une grille : masquer/afficher les enfants, compter les
 * visibles, annoncer l'absence de résultat.
 *
 * Pourquoi un module séparé ? Cette boucle était écrite DEUX FOIS dans le
 * `<script>` de `SourceCatalog.astro` — une fois pour la grille de recos
 * (filtre par type + texte), une fois pour la grille d'épisodes (texte seul
 * + compteur visible) — avec des noms de variables différents et aucun test,
 * puisqu'un `<script>` de page n'est pas exécuté par l'Astro Container API.
 * Deux copies non testées d'un même algorithme finissent toujours par
 * diverger. Elle vit désormais ici, testée dans `tests/js/`.
 *
 * Elle n'est PAS dans `src/utils/search.ts` : ce module se déclare
 * « volontairement pur et sans dépendance », alors qu'on touche ici au DOM.
 * Même dossier, même esprit (un util client extrait de la page), fichier
 * distinct pour ne pas mentir sur le contrat de `search.ts`.
 *
 * A11y (C7) : la région d'annonce reste TOUJOURS dans le DOM et on ne
 * modifie que son `textContent`. La masquer ou la retirer ferait taire son
 * `aria-live="polite"` — les lecteurs d'écran n'annonceraient plus rien.
 */

export interface GridFilterOptions {
  /** Grille dont on filtre les enfants DIRECTS. Absente → repli silencieux. */
  grid?: Element | null;
  /** Prédicat de visibilité, appliqué à chaque enfant direct. */
  matches: (card: HTMLElement) => boolean;
  /** Région `aria-live` recevant le message quand plus rien n'est visible. */
  status?: Element | null;
  /** Message écrit dans `status` à zéro résultat (propre à chaque appelant). */
  emptyMessage: string;
  /** Élément affichant le nombre d'éléments visibles. Optionnel. */
  counter?: Element | null;
  /**
   * Mise en forme du compteur. Par défaut le nombre seul.
   *
   * Sert à faire suivre un libellé accordé : un compteur qui n'écrit que le
   * nombre laisse un « épisodes » figé dans le template, et le filtre client
   * peut le ramener à 1 — d'où « 1 épisodes ».
   */
  formatCounter?: (visible: number) => string;
}

/**
 * Applique le filtre et renvoie le nombre d'éléments restés visibles.
 *
 * Les éléments masqués reçoivent `display: none` ; les visibles reçoivent la
 * chaîne vide — et non `block` — pour rendre la main à la feuille de styles
 * (une carte peut être en `flex`, `grid`…).
 */
export function applyGridFilter(options: GridFilterOptions): number {
  const { grid, matches, status, emptyMessage, counter, formatCounter } = options;
  if (!grid) return 0;

  let visible = 0;
  for (const card of Array.from(grid.children) as HTMLElement[]) {
    const show = matches(card);
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  }

  if (counter) counter.textContent = (formatCounter ?? String)(visible);
  if (status) status.textContent = visible === 0 ? emptyMessage : '';
  return visible;
}
