/**
 * Les décisions que prend la page `/audience` avant d'afficher quoi que ce soit.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Rien de ce qui vit dans un fichier `.astro` n'est mesuré par la couverture :
 * le template est compilé, et la logique qu'il contient échappe aux tests sans
 * que le chiffre bronche. `vitest.config.ts` le dit noir sur blanc — ce qui
 * mérite d'être testé doit être extrait.
 *
 * Ces deux fonctions le méritent : l'une décide QUELLES sources sont lues, et
 * s'être trompé là-dessus avait déjà rendu l'accueil et les 404 invisibles ;
 * l'autre borne une valeur qui vient de l'URL, donc du dehors.
 *
 * UNE SEULE LECTURE (tableau de bord, R2 B du 27/11/2026 ; TB-1 C du
 * 28/11/2026, l'audience au centre)
 * -------------------------------------------------------------------
 * `lireAudience` est la seule porte vers les chiffres : `/audience` l'appelle,
 * et `/api/bord` l'appellera. Deux lectures écrites chacune de son côté
 * finissent par ne plus compter la même chose (familles F2 et F10 du registre
 * des constats). Elle ne dépend pas de l'objet `Astro`, pour servir aussi à une
 * route qui n'est pas une page.
 */

import { agreger, sourcesDisponibles } from './agregat';
import type { Agregat } from './agregat';

export interface Perimetre {
  /** Les sources à agréger. Vide si rien n'a encore été mesuré. */
  sources: string[];
  /** Ce que le titre annonce. */
  libelle: string;
}

/**
 * Quelles sources lire, et sous quel nom l'annoncer.
 *
 * Sans filtre, TOUTES celles trouvées sur le disque — pas seulement celles de
 * `RECO_SOURCES`. `sourceDuChemin` range sous `_site` l'accueil, les pages
 * transverses et les 404 ; cette source n'est jamais déclarée nulle part, et
 * s'en tenir à la configuration revenait à masquer la porte d'entrée du site.
 *
 * Les sources sont nommées dans le libellé même en vue d'ensemble : un total
 * dont on ignore le périmètre ne veut rien dire.
 */
export function perimetreDemande(filtre: string | null, toutes: string[]): Perimetre {
  if (filtre) return { sources: [filtre], libelle: filtre };
  return {
    sources: toutes,
    libelle: toutes.length ? `tout le site · ${toutes.join(', ')}` : 'tout le site',
  };
}

/**
 * Le nombre de jours demandé, ramené entre 1 et 365.
 *
 * La valeur vient de la chaîne de requête : `abc`, `-5`, `1e9` ou rien du tout
 * sont tous des entrées possibles. Une borne haute évite qu'une valeur absurde
 * fasse parcourir des milliers de dossiers à chaque affichage.
 */
export function nbJoursDemande(brut: string | null, defaut = 30): number {
  const n = Number(brut);
  if (!Number.isFinite(n) || n <= 0) return defaut;
  return Math.min(Math.max(Math.floor(n), 1), 365);
}

export interface LectureAudience extends Perimetre {
  /** Les chiffres, ou `null` si la lecture a échoué. */
  donnees: Agregat | null;
  /** Le message de l'échec, à afficher tel quel ; `null` si tout a été lu. */
  erreur: string | null;
}

/**
 * Lit l'audience du périmètre demandé sur les `nbJours` derniers jours.
 *
 * L'hôte du site est celui de `site` (le `site` d'Astro) : derrière le proxy,
 * `url` n'a pas le domaine public (constaté le 2026-10-22). Il ne sert qu'à
 * écarter des provenances les pages du site lui-même.
 *
 * Un échec de `agreger` est rendu, pas levé : la page l'affiche. Celui de
 * `sourcesDisponibles` remonte, comme avant l'extraction.
 */
export function lireAudience({
  racine,
  filtre,
  nbJours,
  site,
  url,
}: {
  /** Le dossier qui contient `tools/output/`. */
  racine: string;
  /** La source demandée ; `null` ou vide pour tout le site. */
  filtre: string | null;
  nbJours: number;
  site?: URL;
  url: URL;
}): LectureAudience {
  const perimetre = perimetreDemande(filtre, sourcesDisponibles(racine));
  try {
    const hoteDuSite = site?.hostname ?? url.hostname;
    const donnees = agreger({ racine, sourceId: perimetre.sources, nbJours, hoteDuSite });
    return { ...perimetre, donnees, erreur: null };
  } catch (e) {
    return { ...perimetre, donnees: null, erreur: e instanceof Error ? e.message : String(e) };
  }
}
