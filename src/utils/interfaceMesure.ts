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
 * l'affichage de la ligne ; après un clic dans le pied, il passe au bouton qui
 * remplace celui qui vient de disparaître.
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

  const agir = (bouton: HTMLElement) => {
    ligne.hidden = true;
    if (bouton.dataset.mesureAct === 'ok') return mesure.fermerLigne();
    const etat = bouton.dataset.mesureAct === 'refuser' ? mesure.refuser() : mesure.accepter();
    rafraichirPied();
    // `data-refusee` / `data-active` : rien n'est annoncé si le choix n'a pas pris.
    retour.textContent = retour.dataset[etat] ?? '';
    if (pied.contains(bouton)) pied.querySelector<HTMLElement>(`[data-pour="${etat}"] button`)?.focus();
  };

  doc.querySelectorAll<HTMLElement>('[data-mesure-act]').forEach((b) => b.addEventListener('click', () => agir(b)));

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
