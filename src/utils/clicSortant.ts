/**
 * clicSortant.ts : le clic sur un lien d'œuvre, mesuré (ADR 0046) et enrichi de
 * trois oui/non (D1, R-1 et R-10, AU-2 B, 2026-11-27).
 *
 * CE QUI PART
 * -----------
 * Un beacon à `POST /api/click` (`src/pages/api/click.ts`) avec l'URL cliquée,
 * la catégorie, la source, l'éventuelle reco, le chemin de la page (`ref`) et,
 * quand la mesure gardée dans le navigateur les connaît, `revenant`,
 * `aVuEpisode`, `aVuFiche` : rien d'autre, aucun identifiant, ni date de
 * naissance de la mesure, ni liste de pages. Ils servent à compter, en parts,
 * le chemin épisode → fiche œuvre → clic.
 *
 * LECTURE SEULE (C1)
 * ------------------
 * `mesure.ouiNon` ne crée ni ne modifie l'état : seul le signal « page vue »
 * (`noterPage`) le crée. Sans état (première page, stockage coupé), le clic
 * part sans oui/non : le serveur y lit `null`, jamais un « non » inventé.
 *
 * QUAND IL NE PART PAS
 * --------------------
 * Refus de la personne, Global Privacy Control ou Do Not Track à « 1 » (R-2,
 * R-10 : DNT traité comme GPC) : l'état de la mesure est lu AU CLIC, pas au
 * chargement, pour que « Refuser » prenne effet sans recharger la page. Page
 * non mesurable (`/meta`, `noindex`) : le script n'est même pas armé.
 * Toute erreur est avalée : le clic doit aboutir quoi qu'il arrive.
 */
import { pageMesurable } from './signalVue';

interface Mesure {
  etat(): string;
  ouiNon(chemin: string): { revenant: boolean; aVuEpisode: boolean; aVuFiche: boolean } | null;
}

export interface Dependances {
  navigator: { sendBeacon?: (url: string, donnees?: BodyInit | null) => boolean };
  document: Document;
  location: { pathname: string };
  fetch: (url: string, init: RequestInit) => Promise<unknown>;
  mesure: Mesure;
}

/** Rend `false` si la page n'est pas mesurable (rien n'est armé). */
export function cablerClicSortant({ navigator, document, location, fetch, mesure }: Dependances): boolean {
  // F-H-1 : pas de suivi sur `/meta/*` ni sur les pages `noindex` (ADR 0040, ADR 0046).
  if (!pageMesurable(location, document)) return false;
  document.addEventListener(
    'click',
    (e) => {
      const el = e.target;
      if (!(el instanceof Element)) return;
      const a = el.closest('a[data-track="click"]');
      if (!(a instanceof HTMLAnchorElement)) return;
      const { category, sourceId } = a.dataset;
      if (!a.href || !category || !sourceId) return;
      try {
        // Refus, GPC, DNT : on ne regarde rien, on n'envoie rien.
        const etat = mesure.etat();
        if (etat === 'refusee' || etat === 'navigateur') return;
        const vu = mesure.ouiNon(location.pathname);
        const corps = JSON.stringify({
          url: a.href,
          category,
          sourceId,
          recoId: a.dataset.recoId || null,
          ref: location.pathname,
          // Champ par champ : rien d'autre ne sort ; absents si la mesure ne sait pas.
          ...(vu && { revenant: vu.revenant, aVuEpisode: vu.aVuEpisode, aVuFiche: vu.aVuFiche }),
        });
        // Le beacon part en `application/json` : le serveur lit aussi le texte.
        if (navigator.sendBeacon?.('/api/click', new Blob([corps], { type: 'application/json' }))) return;
        fetch('/api/click', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: corps,
          keepalive: true,
        }).catch(() => {});
      } catch {
        /* silencieux : le clic doit aboutir quoi qu'il arrive */
      }
    },
    { capture: true, passive: true },
  );
  return true;
}
