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
 */

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
