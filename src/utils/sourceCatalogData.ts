/**
 * Données du catalogue d'une source, partagées par trois pages.
 *
 * Extrait de `SourceCatalog.astro` le 2026-08-16, quand la vue « toutes les
 * recos » a dû sortir de la page d'accueil : la même préparation sert
 * désormais au catalogue, à la page `/[source]/recos` et à son fragment. La
 * recopier trois fois aurait garanti qu'elles divergent — l'ordre de tri et le
 * filtrage des recos écartées sont exactement le genre de détail qui se perd
 * dans une copie.
 */
import { getCollection } from 'astro:content';

import { sortRecosByTimestamp } from './recoOrder';

export interface CatalogData {
  /** Recos ACTIVES de la source, triées chronologiquement. */
  recos: any[];
  /** Épisodes indexés par guid — pour afficher numéro et titre sur les cartes. */
  epByGuid: Map<string, any>;
  /** `[type, nombre]`, du plus fréquent au moins fréquent (ordre des filtres). */
  types: [string, number][];
}

export async function loadCatalogData(sourceId: string): Promise<CatalogData> {
  // Tri CHRONOLOGIQUE explicite : sans lui, l'ordre serait celui d'énumération
  // du chargeur de fichiers d'Astro — un détail d'implémentation que la
  // migration 5 → 7 a effectivement changé.
  const recos = sortRecosByTimestamp(
    (await getCollection('recos'))
      .filter((r) => r.data.sourceId.id === sourceId && r.data.status !== 'discarded')
      .map((r) => r.data),
  );

  const episodes = (await getCollection('episodes')).filter(
    (e) => e.data.sourceId.id === sourceId,
  );
  const epByGuid = new Map(episodes.map((e) => [e.data.guid, e.data]));

  // Une reco multi-types compte dans CHAQUE type : le filtre est inclusif.
  const counts = new Map<string, number>();
  for (const r of recos) for (const t of r.types) counts.set(t, (counts.get(t) ?? 0) + 1);
  const types = [...counts.entries()].sort((a, b) => b[1] - a[1]) as [string, number][];

  return { recos, epByGuid, types };
}
