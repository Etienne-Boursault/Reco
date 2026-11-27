/**
 * Les revenants et le chemin épisode → fiche → clic, en parts agrégées
 * (décision d'Étienne du 27/11, « AU-2 B » ; règles R-1 et R-13).
 *
 * CE QUE C'EST
 *   - revenants : parmi les visiteurs-jours CONFIRMÉS (`classement.ts`), la
 *     part dont le signal porte `revenant: true` ;
 *   - chemin : parmi les visiteurs-jours confirmés qui ont vu un épisode
 *     (`aVuEpisode`), la part qui a vu une fiche (`aVuFiche`) ;
 *   - clics : parmi les clics sortants, la part qui porte `aVuEpisode`, et la
 *     part qui porte `aVuFiche` (lignes de la tranche D1).
 *
 * CE QUE CE N'EST PAS (R-13)
 *   - L'ORDRE des étapes n'est jamais mesuré : ce serait un parcours
 *     individuel. On ne compte que des oui/non du jour, jamais une séquence.
 *   - Aucune part n'est rendue sur un petit effectif : voir `SEUIL_PARCOURS`.
 *
 * UN VISITEUR-JOUR est une empreinte et un jour. Un visiteur qui a plusieurs
 * signaux dans la journée compte une fois, avec le « ou » de ses signaux :
 * s'il a vu un épisode à un moment de la journée, il l'a vu. Les oui/non
 * absents (ancien script, lignes d'avant D1) ou à `null` sont « inconnus » :
 * hors du numérateur comme du dénominateur.
 *
 * LES CLICS ne portent aucun identifiant : on compte des clics, pas des
 * visiteurs, et tous les clics d'un jour y entrent (la confirmation d'un
 * visiteur ne peut pas se lire sur un clic).
 *
 * LIMITE : Safari plafonne le stockage d'un site à 7 jours sans visite (ITP).
 * Un revenant de plus d'une semaine y devient un nouveau visiteur : la part
 * des revenants est sous-comptée, et la page le dit (tranche E1).
 */
import type { Classe, LigneVisite, Signal } from './classement';

/**
 * Plancher de chaque case. `shortcut: constante en dur, à relever ici sans
 * migration : rien d'écrit sur disque ne la porte`.
 */
export const SEUIL_PARCOURS = 10;

/** Un oui/non connu : les inconnus ne sont dans aucune des deux cases. */
export interface Compte {
  oui: number;
  non: number;
}

/** Les comptes bruts d'une période, additionnables jour après jour. */
export interface Brut {
  revenants: Compte;
  /** Parmi les visiteurs-jours ayant vu un épisode : a vu une fiche ou non. */
  fiche: Compte;
  clicEpisode: Compte;
  clicFiche: Compte;
}

/** Une part affichable : `pct` est en pourcent, au dixième. */
export interface Part {
  oui: number;
  total: number;
  pct: number;
}

/** `null` : « trop peu de données ». */
export interface Parcours {
  revenants: Part | null;
  vuFiche: Part | null;
  clicsEpisode: Part | null;
  clicsFiche: Part | null;
}

/** Ce que ce module lit d'un clic ; les trois champs manquent avant D1. */
export interface LigneClic {
  aVuEpisode?: boolean | null;
  aVuFiche?: boolean | null;
}

type Tri = boolean | null | undefined;

const vide = (): Compte => ({ oui: 0, non: 0 });

export function brutVide(): Brut {
  return { revenants: vide(), fiche: vide(), clicEpisode: vide(), clicFiche: vide() };
}

/** Seul un vrai booléen est connu ; le reste est « inconnu ». */
function ajouter(c: Compte, v: Tri): void {
  if (v === true) c.oui++;
  else if (v === false) c.non++;
}

/** Le « ou » des signaux d'un jour : un oui l'emporte, sinon un non, sinon inconnu. */
function ou(valeurs: Tri[]): Tri {
  if (valeurs.includes(true)) return true;
  return valeurs.includes(false) ? false : null;
}

/**
 * Les comptes d'une journée. `classes` vient de `classer` (même ordre que
 * `visites`) ; `null` avant la bascule : sans tri fiable, on ne compte aucun
 * signal. Les clics, eux, sont comptés dans tous les cas.
 */
export function compterJour(
  visites: LigneVisite[],
  classes: Classe[] | null,
  signaux: Signal[],
  clics: LigneClic[],
): Brut {
  const brut = brutVide();
  for (const c of clics) {
    ajouter(brut.clicEpisode, c.aVuEpisode);
    ajouter(brut.clicFiche, c.aVuFiche);
  }
  if (!classes) return brut;

  const confirmes = new Set(
    visites.filter((v, i) => classes[i] === 'confirme' && v.visiteur).map((v) => v.visiteur),
  );
  const parVisiteur = new Map<string, Signal[]>();
  for (const s of signaux) {
    if (s.visiteur && confirmes.has(s.visiteur)) {
      parVisiteur.set(s.visiteur, [...(parVisiteur.get(s.visiteur) ?? []), s]);
    }
  }
  for (const liste of parVisiteur.values()) {
    ajouter(brut.revenants, ou(liste.map((s) => s.revenant)));
    // Le chemin ne compte que ceux qui ont vu un épisode.
    if (ou(liste.map((s) => s.aVuEpisode)) === true) ajouter(brut.fiche, ou(liste.map((s) => s.aVuFiche)));
  }
  return brut;
}

export function sommer(liste: Brut[]): Brut {
  const somme = brutVide();
  for (const b of liste) {
    for (const cle of Object.keys(somme) as (keyof Brut)[]) {
      somme[cle].oui += b[cle].oui;
      somme[cle].non += b[cle].non;
    }
  }
  return somme;
}

/**
 * Une part, ou `null` sous le seuil. Les deux cases (oui, non) doivent
 * atteindre le plancher : cela couvre aussi le dénominateur (il vaut au moins
 * deux planchers) et empêche de déduire une petite case d'un total.
 */
function part({ oui, non }: Compte): Part | null {
  if (oui < SEUIL_PARCOURS || non < SEUIL_PARCOURS) return null;
  const total = oui + non;
  return { oui, total, pct: Math.round((oui / total) * 1000) / 10 };
}

export function parts(b: Brut): Parcours {
  return {
    revenants: part(b.revenants),
    vuFiche: part(b.fiche),
    clicsEpisode: part(b.clicEpisode),
    clicsFiche: part(b.clicFiche),
  };
}
