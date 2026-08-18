/**
 * lienEvitement.ts — le lien « aller au contenu » ne laisse plus son ancre
 * dans l'URL.
 *
 * CE QUI SE PASSAIT
 * -----------------
 * Le lien pointe `#main`. En l'activant, le navigateur inscrit l'ancre dans
 * l'URL : `http://…/#main` restait affiché dans la barre d'adresse, entrait
 * dans l'historique — le bouton Retour ramenait à la même page sans ancre —
 * et se retrouvait copié-collé par qui partageait le lien.
 *
 * Relevé à la relecture du 2026-08-18. C'est le comportement natif d'un lien
 * d'ancre, et beaucoup de sites le laissent tel quel. Mais personne ne l'a
 * demandé, et il n'apporte rien : l'ancre a rempli son office à l'instant du
 * saut.
 *
 * CE QU'ON PRÉSERVE
 * -----------------
 * Le FOCUS, qui est tout l'intérêt du lien. Sans lui, activer « aller au
 * contenu » déplacerait le défilement en laissant le clavier où il était, et
 * la tabulation suivante repartirait du début — le défaut corrigé le même jour
 * en posant `tabindex="-1"` sur la cible.
 *
 * On pose donc le focus nous-mêmes AVANT de nettoyer l'URL, plutôt que de
 * compter sur l'effet de bord du saut natif.
 */

/**
 * Câble le nettoyage sur le lien d'évitement du document.
 *
 * Renvoie `false` si le lien est absent ou déjà câblé — de quoi vérifier le
 * câblage dans un test.
 */
export function cablerLienEvitement(): boolean {
  const lien = document.querySelector<HTMLAnchorElement>('.skip-link');
  if (!lien || lien.dataset.evitementCable === '1') return false;
  lien.dataset.evitementCable = '1';

  lien.addEventListener('click', (evenement) => {
    const cible = document.querySelector<HTMLElement>('#main');
    if (!cible) return; // pas de cible : on laisse le navigateur faire

    // On prend la main sur le saut : le focus d'abord, l'URL ensuite.
    evenement.preventDefault();
    cible.focus();
    cible.scrollIntoView();

    try {
      // `replaceState` et non `pushState` : le bouton Retour doit ramener à
      // la page précédente, pas à la même page débarrassée de son ancre.
      history.replaceState(null, '', location.pathname + location.search);
    } catch {
      // Contexte restreint (sandbox, `file://`) : garder l'ancre est un
      // moindre mal, et lever ici casserait le saut lui-même.
    }
  });

  return true;
}
