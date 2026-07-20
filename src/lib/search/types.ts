/**
 * src/lib/search/types.ts — Types partagés pour l'index de recherche.
 *
 * Une seule structure `SearchDoc` (item | episode | guest) discriminée par
 * `kind`, afin de pouvoir tout indexer dans un seul MiniSearch.
 */

export type SearchKind = 'item' | 'episode' | 'guest';

/** Document indexable dans MiniSearch (champs sérialisés tels quels en JSON). */
export interface SearchDoc {
  /** Identifiant unique stable (préfixé par kind pour éviter les collisions). */
  id: string;
  kind: SearchKind;
  /** Titre principal (œuvre, épisode, nom invité). */
  title: string;
  /** Sous-titre (créateur·rice, source title…). */
  subtitle?: string;
  /** Champ libre — hôtes/invités/types. Indexé. */
  text?: string;
  /** Slug ou ID de source (utile pour le filtrage et l'URL). */
  source?: string;
  /** Lien direct vers la fiche correspondante. */
  url: string;
}

/** Format sérialisé `dist/_search/index.json`. */
export interface SearchIndexFile {
  /** Version du schéma — bumper si on change la forme des docs. */
  version: number;
  /** Date ISO du build qui a produit l'index. */
  generatedAt: string;
  /** Nombre total de documents (pour info / monitoring). */
  count: number;
  /** Liste plate. Le client (re)construit son MiniSearch à partir de ça. */
  docs: SearchDoc[];
}

export const SEARCH_INDEX_VERSION = 1;
