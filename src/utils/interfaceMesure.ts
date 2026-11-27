/**
 * interfaceMesure.ts : branche la ligne de première visite et l'interrupteur
 * du pied de page (`MesureAudience.astro`) sur la mesure gardée dans le
 * navigateur (`mesureNavigateur.ts`) (« AU-2 B », 2026-11-27 ; précision
 * d'Étienne, 11 h 19 : « transparent pour l'utilisateur, il faut qu'il puisse
 * opt-out plus facilement qu'en allant dans une page difficile d'accès »).
 *
 * LA LIGNE ET LE PIED D'ACCORD (R-13)
 * -----------------------------------
 * Tout se lit sur `mesure.etat()` : le pied montre le morceau `data-pour`
 * qui porte le nom de l'état, un clic dans la ligne met le pied à jour sur
 * place, et inversement. L'événement `storage` fait suivre un autre onglet.
 *
 * QUAND LA LIGNE APPARAÎT
 * -----------------------
 * `apresEnvoi` est rappelée par `signalVue.ts` juste après `noterPage`, qui est
 * seule à créer l'état à la première visite. Ni la ligne ni le pied n'appellent
 * `noterPage` : cela créerait l'état sans signal. Une page qui n'envoie pas de
 * signal (`/meta`, `noindex`, robot déclaré) n'affiche donc pas la ligne.
 *
 * CE QUI EST ASSUMÉ
 * -----------------
 * « Refuser » et « Désactiver » n'agissent qu'à partir de la page suivante : le
 * signal de la page en cours est peut-être déjà parti.
 *
 * Accessibilité : le pied est posé dans le HTML sans zone d'annonce ; seul un
 * clic annonce son résultat (`role="status"`). Le focus n'est jamais volé à
 * l'affichage de la ligne ; après un clic dans le pied ou dans la ligne, il
 * passe au bouton du pied qui remplace celui qui vient de disparaître, mais
 * seulement pour une activation au clavier (`detail` à 0) : à la souris ou au
 * toucher, le focus ne bouge pas, pour que la page ne défile pas jusqu'au pied.
 */
import type { EtatMesure } from './mesureNavigateur';

/** Ce que l'interface lit de la mesure (type local : pas de cycle d'import). */
interface Mesure {
  etat(): EtatMesure;
  ligneAAfficher(): boolean;
  ligneVue(): void;
  fermerLigne(): void;
  refuser(): EtatMesure;
  accepter(): EtatMesure;
}

export function cablerInterfaceMesure(
  doc: Document,
  win: Pick<Window, 'addEventListener'>,
  mesure: Mesure,
): { apresEnvoi(): void } {
  const pied = doc.querySelector<HTMLElement>('[data-mesure-pied]');
  const ligne = doc.querySelector<HTMLElement>('[data-mesure-ligne]');
  const retour = doc.querySelector<HTMLElement>('[data-mesure-retour]');
  // Une page sans pied de page n'a rien à brancher.
  if (!pied || !ligne || !retour) return { apresEnvoi() {} };

  const rafraichirPied = () => {
    const etat = mesure.etat();
    pied.querySelectorAll<HTMLElement>('[data-pour]').forEach((el) => {
      el.hidden = el.dataset.pour !== etat;
    });
  };

  /**
   * Le focus passe au bouton du pied de l'état courant, ou, s'il n'y en a pas
   * (GPC, stockage coupé), à son texte, rendu focalisable. Sans cela, le
   * focus d'un bouton qui disparaît (ligne cachée, ou bouton du pied remplacé)
   * tombe sur `body` : un clavier perd sa place (tour 1 de revue, PR #224).
   */
  const focusDansLePied = (etat: EtatMesure) => {
    const cible =
      pied.querySelector<HTMLElement>(`[data-pour="${etat}"] button`) ?? pied.querySelector<HTMLElement>(`[data-pour="${etat}"]`);
    if (!cible) return;
    if (cible.tagName !== 'BUTTON') cible.tabIndex = -1;
    cible.focus();
  };

  /**
   * `auClavier` : le focus ne se déplace que pour une activation au clavier.
   * La ligne est fixe en bas de la fenêtre et le pied en bas du document :
   * `focus()` ferait défiler la page, et un lecteur qui clique « OK » à
   * mi-page sauterait au pied (tour 2 de revue, PR #224).
   */
  const agir = (bouton: HTMLElement, auClavier: boolean) => {
    const placerLeFocus = (etat: EtatMesure) => auClavier && focusDansLePied(etat);
    ligne.hidden = true;
    if (bouton.dataset.mesureAct === 'ok') {
      mesure.fermerLigne();
      return placerLeFocus(mesure.etat());
    }
    const etat = bouton.dataset.mesureAct === 'refuser' ? mesure.refuser() : mesure.accepter();
    rafraichirPied();
    // `data-refusee` / `data-active` : rien n'est annoncé si le choix n'a pas pris.
    retour.textContent = retour.dataset[etat] ?? '';
    placerLeFocus(etat);
  };

  doc.querySelectorAll<HTMLElement>('[data-mesure-act]').forEach((b) =>
    b.addEventListener('click', (e) => agir(b, (e as MouseEvent).detail === 0)),
  );

  win.addEventListener('storage', () => {
    rafraichirPied();
    if (!mesure.ligneAAfficher()) ligne.hidden = true;
  });

  rafraichirPied();
  return {
    apresEnvoi() {
      rafraichirPied();
      if (!mesure.ligneAAfficher()) return;
      ligne.hidden = false;
      mesure.ligneVue();
    },
  };
}
