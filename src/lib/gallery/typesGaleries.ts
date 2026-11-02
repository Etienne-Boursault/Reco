/**
 * src/lib/gallery/typesGaleries.ts — la table des galeries par type.
 *
 * POURQUOI ELLE EXISTE
 * --------------------
 * Cinq types avaient leur page — `films`, `series`, `musique`, `livres`,
 * `chaines`. Les neuf autres n'en avaient aucune : le sommaire `/galeries` les
 * renvoyait vers `/recos` avec un filtre pré-posé, ce qui n'était pas ce qui
 * avait été demandé — « je souhaitais avoir un accès par types comme /series
 * mais pour chacun des types et donc qu'ils aient tous une galerie »
 * (relecture du 2026-08-19).
 *
 * Plutôt que neuf fichiers `.astro` quasi identiques, une route dynamique
 * `[galerie].astro` les sert tous. Cette table en est la source unique : elle
 * dit quel slug rend quels types, sous quel titre, avec quel accord.
 *
 * POURQUOI DEUX LISTES
 * --------------------
 * `PAGES_DEDIEES` décrit les cinq pages qui ont leur propre fichier. Elles ne
 * passent PAS par la route dynamique — Astro construirait deux pages pour la
 * même adresse. Elles figurent ici pour une seule raison : permettre de
 * vérifier, par un test, qu'aucun type du corpus n'est laissé sans galerie.
 */

import type { ItemType } from '../../content.config';

/** Une galerie : un slug d'URL, les types qu'elle rassemble, ses libellés. */
export interface Galerie {
  /** Le segment d'URL — `/un-bon-moment/<slug>`. */
  slug: string;
  /**
   * Les types d'item retenus. Plusieurs quand ils forment un tout.
   *
   * `ItemType` et non `string` : en `string[]`, une faute de frappe passait le
   * compilateur et produisait une galerie vide en silence.
   */
  types: ItemType[];
  /** Le titre de la page, aussi porté par `<h1>`. */
  titre: string;
  /**
   * Le nom du type, seul. Le sommaire aligne quatorze entrées : « Tous les
   * films » y répétait un article que la colonne rendait inutile — « mets
   * simplement le type », relecture du 2026-08-19.
   */
  court: string;
  /**
   * Le compteur au singulier — « spectacle cité ». « cité » et non
   * « recommandé » : la galerie compte aussi les œuvres seulement évoquées
   * (`selectByType` garde les citations), corrigé le 2026-11-02.
   */
  unGe: string;
  /** Le compteur au pluriel — « spectacles cités ». */
  plusieurs: string;
  /** Nom féminin : accorde « recommandées ou seulement évoquées ». */
  feminin: boolean;
  /** La phrase affichée quand la galerie est vide. */
  vide: string;
}

/**
 * Les cinq galeries à fichier dédié. Elles ne sont pas servies par la route
 * dynamique ; elles ne sont là que pour la vérification de couverture.
 */
export const PAGES_DEDIEES: Galerie[] = [
  { slug: 'films', court: 'Films', types: ['film'], titre: 'Tous les films',
    unGe: 'film cité', plusieurs: 'films cités', feminin: false,
    vide: 'Aucun film recommandé pour l’instant.' },
  { slug: 'series', court: 'Séries', types: ['serie'], titre: 'Toutes les séries',
    unGe: 'série citée', plusieurs: 'séries citées', feminin: true,
    vide: 'Aucune série recommandée pour l’instant.' },
  { slug: 'musique', court: 'Musique', types: ['musique', 'album'], titre: 'Toute la musique',
    unGe: 'œuvre musicale citée', plusieurs: 'œuvres musicales citées', feminin: true,
    vide: 'Aucune musique recommandée pour l’instant.' },
  { slug: 'livres', court: 'Livres et BD', types: ['livre', 'bd'], titre: 'Tous les livres',
    unGe: 'livre ou BD cité', plusieurs: 'livres et BD cités', feminin: false,
    vide: 'Aucun livre recommandé pour l’instant.' },
  { slug: 'chaines', court: 'Chaînes', types: ['chaine'], titre: 'Toutes les chaînes YouTube',
    unGe: 'chaîne YouTube citée', plusieurs: 'chaînes YouTube citées', feminin: true,
    vide: 'Aucune chaîne recommandée pour l’instant.' },
];

/**
 * Les galeries servies par la route dynamique.
 *
 * `albums` et `bd` recoupent volontairement `musique` et `livres` : la page
 * groupée reste la porte d'entrée naturelle, mais l'éditeur demandait un accès
 * par type, et un album n'est pas un morceau.
 */
export const GALERIES_PAR_TYPE: Galerie[] = [
  { slug: 'artistes', court: 'Artistes', types: ['artiste'], titre: 'Tous les artistes',
    unGe: 'artiste cité', plusieurs: 'artistes cités', feminin: false,
    vide: 'Aucun artiste recommandé pour l’instant.' },
  { slug: 'albums', court: 'Albums', types: ['album'], titre: 'Tous les albums',
    unGe: 'album cité', plusieurs: 'albums cités', feminin: false,
    vide: 'Aucun album recommandé pour l’instant.' },
  { slug: 'bd', court: 'BD', types: ['bd'], titre: 'Toutes les BD',
    unGe: 'bande dessinée citée', plusieurs: 'bandes dessinées citées', feminin: true,
    vide: 'Aucune bande dessinée recommandée pour l’instant.' },
  { slug: 'spectacles', court: 'Spectacles', types: ['spectacle'], titre: 'Tous les spectacles',
    unGe: 'spectacle cité', plusieurs: 'spectacles cités', feminin: false,
    vide: 'Aucun spectacle recommandé pour l’instant.' },
  { slug: 'videos', court: 'Vidéos', types: ['video'], titre: 'Toutes les vidéos',
    unGe: 'vidéo citée', plusieurs: 'vidéos citées', feminin: true,
    vide: 'Aucune vidéo recommandée pour l’instant.' },
  { slug: 'podcasts', court: 'Podcasts', types: ['podcast'], titre: 'Tous les podcasts',
    unGe: 'podcast cité', plusieurs: 'podcasts cités', feminin: false,
    vide: 'Aucun podcast recommandé pour l’instant.' },
  { slug: 'jeux', court: 'Jeux', types: ['jeu'], titre: 'Tous les jeux',
    unGe: 'jeu cité', plusieurs: 'jeux cités', feminin: false,
    vide: 'Aucun jeu recommandé pour l’instant.' },
  { slug: 'lieux', court: 'Lieux', types: ['lieu'], titre: 'Tous les lieux',
    unGe: 'lieu cité', plusieurs: 'lieux cités', feminin: false,
    vide: 'Aucun lieu recommandé pour l’instant.' },
  { slug: 'applications', court: 'Applications', types: ['application'], titre: 'Toutes les applications',
    unGe: 'application citée', plusieurs: 'applications citées', feminin: true,
    vide: 'Aucune application recommandée pour l’instant.' },
  // `autre` est le type de repli : ce qui n'entre dans aucune case. Sans page,
  // ces œuvres ne s'atteignaient que par la recherche.
  { slug: 'autres', court: 'Autres', types: ['autre'], titre: 'Tout le reste',
    unGe: 'œuvre hors catégorie citée', plusieurs: 'œuvres hors catégorie citées', feminin: true,
    vide: 'Rien hors catégorie pour l’instant.' },
];

/** Retrouve une galerie dynamique par son slug. Les pages dédiées sortent. */
export function galerieDuSlug(slug: string): Galerie | undefined {
  return GALERIES_PAR_TYPE.find((g) => g.slug === slug);
}
