/**
 * src/lib/work/similarity.ts — Frontière `SimilarWorksProvider` (ADR 0044).
 *
 * Interface stable consommée par la page canonique d'œuvre
 * (`/<source>/oeuvre/<itemId>`). Deux implémentations livrées :
 *
 * - `creatorBasedProvider` : logique historique (égalité de créateur),
 *   héritée de `aggregator.ts:similarByCreator`. Toujours disponible,
 *   aucun pré-requis pipeline.
 * - `embeddingsBasedProvider` : lit un JSON pré-généré par
 *   `tools/export_similar_works.py` (cf. ADR 0044 § Build-time). Si le
 *   JSON est absent ou ne contient pas l'item demandé, retourne `[]` —
 *   le `compositeProvider` peut alors fallback sur le creator-based.
 *
 * Module **pur** (aucune dépendance Astro). Le chargement disque du JSON
 * est injecté via `dataLoader` pour rester testable en Node sans monter
 * un faux filesystem.
 */
import type { ItemLike } from './aggregator';

/** Hit de similarité — `score` présent si fourni par les embeddings. */
export interface SimilarWork {
  id: string;
  title: string;
  score?: number;
  reason: 'creator' | 'embeddings';
}

/** Provider qui propose des œuvres similaires à `current`. */
export interface SimilarWorksProvider {
  findSimilar(
    current: ItemLike,
    candidates: ItemLike[],
    opts?: { limit?: number },
  ): SimilarWork[];
}

/**
 * Provider "créateur" — extrait historique de `aggregator.ts`.
 * Conserve la sémantique exacte de `similarByCreator` :
 *   - filtre par créateur (case/strip insensible),
 *   - exclut l'item courant,
 *   - cap à `limit` (3 par défaut),
 *   - retourne `[]` si l'item courant n'a pas de créateur.
 */
export const creatorBasedProvider: SimilarWorksProvider = {
  findSimilar(current, candidates, opts) {
    const limit = opts?.limit ?? 3;
    const creator = (current.creator ?? '').trim().toLowerCase();
    if (!creator) return [];
    const out: SimilarWork[] = [];
    for (const c of candidates) {
      if (c.id === current.id) continue;
      if ((c.creator ?? '').trim().toLowerCase() === creator) {
        out.push({ id: c.id, title: c.title, reason: 'creator' });
        if (out.length >= limit) break;
      }
    }
    return out;
  },
};

/** Forme JSON produite par `tools/export_similar_works.py` (ADR 0044). */
export interface SimilarWorksData {
  schemaVersion: number;
  source: string;
  model: string;
  k: number;
  generated_at: string;
  items: Record<string, { id: string; score: number }[]>;
}

/**
 * Loader pour le JSON pré-généré. Implémenté côté Astro via `node:fs`
 * (build-time), injectable en mémoire pour les tests.
 *
 * Retourne `null` si la source n'a pas de données (ex : déploiement
 * sans pipeline embeddings).
 */
export type SimilarWorksDataLoader = (
  sourceId: string,
) => SimilarWorksData | null;

/**
 * Provider "embeddings" — lit le JSON pré-généré.
 *
 * Si le JSON est absent OU si l'item courant n'a pas d'entrée → `[]`.
 * Les voisins sont résolus contre `candidates` ; un voisin référencé
 * mais introuvable dans `candidates` est ignoré (cas typique : un item
 * supprimé entre l'export et le build).
 */
export function embeddingsBasedProvider(
  sourceId: string,
  dataLoader: SimilarWorksDataLoader,
): SimilarWorksProvider {
  return {
    findSimilar(current, candidates, opts) {
      const limit = opts?.limit ?? 3;
      const data = dataLoader(sourceId);
      if (!data) return [];
      const neighbors = data.items[current.id];
      if (!neighbors || neighbors.length === 0) return [];
      const byId = new Map<string, ItemLike>();
      for (const c of candidates) byId.set(c.id, c);
      const out: SimilarWork[] = [];
      for (const n of neighbors) {
        if (n.id === current.id) continue;
        const item = byId.get(n.id);
        if (!item) continue;
        out.push({
          id: item.id,
          title: item.title,
          score: n.score,
          reason: 'embeddings',
        });
        if (out.length >= limit) break;
      }
      return out;
    },
  };
}

/**
 * Provider composite : embeddings d'abord, fallback creator si vide.
 * C'est ce que retourne `getSimilarWorksProvider` par défaut quand un
 * `dataLoader` est fourni.
 */
export function compositeProvider(
  embeddings: SimilarWorksProvider,
  fallback: SimilarWorksProvider,
): SimilarWorksProvider {
  return {
    findSimilar(current, candidates, opts) {
      const fromEmb = embeddings.findSimilar(current, candidates, opts);
      if (fromEmb.length > 0) return fromEmb;
      return fallback.findSimilar(current, candidates, opts);
    },
  };
}

/**
 * Sélecteur principal — point d'entrée pour `[itemId].astro` (futur
 * câblage, hors Phase 3.5).
 *
 * - Si `dataLoader` est fourni → composite (embeddings + fallback).
 * - Sinon → `creatorBasedProvider` direct.
 */
export function getSimilarWorksProvider(
  sourceId: string,
  opts?: { dataLoader?: SimilarWorksDataLoader },
): SimilarWorksProvider {
  if (opts?.dataLoader) {
    return compositeProvider(
      embeddingsBasedProvider(sourceId, opts.dataLoader),
      creatorBasedProvider,
    );
  }
  return creatorBasedProvider;
}
