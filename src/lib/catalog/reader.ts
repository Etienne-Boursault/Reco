/**
 * Port de lecture du catalogue : la seule porte d'entrée des pages vers les données.
 *
 * POURQUOI CE PORT EXISTE
 * -----------------------
 * La V2 doit servir le catalogue depuis une révision publiée sans rebuild, et
 * chaque requête devra lire un seul instantané de cette révision (ADR 0058,
 * proposée). Or les pages, les composants et les endpoints appelaient
 * `getCollection` directement, à une trentaine d'endroits : brancher une autre
 * source aurait demandé de les reprendre tous, et d'en oublier un. Ils passent
 * désormais tous par `lecteur()`, et un test interdit d'importer
 * `getCollection` ailleurs qu'ici.
 *
 * AUJOURD'HUI
 * -----------
 * `lecteur()` rend toujours l'adaptateur des collections Astro, construites au
 * build : le site produit est identique, octet pour octet. Le contexte de la
 * requête (`Astro` dans une page ou un composant, le contexte d'un endpoint)
 * est déjà passé à chaque appel ; c'est là que le lecteur de l'instantané
 * (`locals.catalogue`) viendra se brancher, sans retoucher les appelants.
 * `getStaticPaths` n'a pas de requête : il appelle `lecteur()` sans contexte.
 */
import { getCollection, type CollectionEntry, type CollectionKey } from 'astro:content';

/** Lecture du catalogue public. */
export interface CatalogReader {
  /** Toutes les entrées d'une collection, dans l'ordre que rend `getCollection`. */
  collection<C extends CollectionKey>(nom: C): Promise<CollectionEntry<C>[]>;
}

/** Contexte d'une requête : `Astro` dans une page, le contexte d'un endpoint. */
export interface ContexteDeLecture {
  locals?: unknown;
}

/** Adaptateur « embarqué » : les collections Astro, figées au build. */
export const collectionsReader: CatalogReader = {
  collection: (nom) => getCollection(nom),
};

/**
 * Le lecteur à utiliser pour une requête. Le contexte n'est pas encore lu :
 * il le sera quand une révision pourra être servie à la place des collections.
 */
export function lecteur(_contexte?: ContexteDeLecture): CatalogReader {
  return collectionsReader;
}
