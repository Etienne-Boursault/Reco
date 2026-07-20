/**
 * src/lib/search/client.ts — Helpers MiniSearch côté client.
 *
 * Construction de l'instance MiniSearch + helpers de recherche groupés
 * par `kind`. Le fichier est importé à la fois par le palette (Cmd+K) et
 * la page `/recherche`.
 *
 * Conçu pour le navigateur ET pour les tests Node (vitest) — on n'utilise
 * aucune API DOM ici.
 */

import MiniSearch, { type SearchResult } from 'minisearch';
import { normalizeTerm, tokenizeFR } from './normalize';
import type { SearchDoc, SearchKind } from './types';

/**
 * Crée un MiniSearch configuré FR-friendly à partir des docs.
 *  - tokenizer FR (split sur non-alphanum, strip accents)
 *  - processTerm FR (lowercase + strip accents)
 *  - prefix + fuzzy par défaut sur les requêtes utilisateur
 *  - boost titre (×3) > subtitle (×2) > text (×1)
 */
export function createSearchIndex(docs: readonly SearchDoc[]): MiniSearch<SearchDoc> {
  const mini = new MiniSearch<SearchDoc>({
    fields: ['title', 'subtitle', 'text'],
    storeFields: ['id', 'kind', 'title', 'subtitle', 'url', 'source'],
    idField: 'id',
    tokenize: (text) => tokenizeFR(text),
    processTerm: (term) => {
      const norm = normalizeTerm(term);
      return norm.length > 0 ? norm : null;
    },
    searchOptions: {
      boost: { title: 3, subtitle: 2, text: 1 },
      prefix: true,
      fuzzy: 0.2,
      combineWith: 'AND',
    },
  });
  mini.addAll(docs as SearchDoc[]);
  return mini;
}

export interface PaletteHit {
  id: string;
  kind: SearchKind;
  title: string;
  subtitle?: string;
  url: string;
  source?: string;
  score: number;
}

export interface GroupedHits {
  items: PaletteHit[];
  episodes: PaletteHit[];
  guests: PaletteHit[];
  total: number;
}

/** Convertit un `SearchResult` MiniSearch en `PaletteHit` typé. */
function toHit(result: SearchResult): PaletteHit {
  return {
    id: String(result.id),
    kind: result.kind as SearchKind,
    title: String(result.title ?? ''),
    subtitle: result.subtitle ? String(result.subtitle) : undefined,
    url: String(result.url ?? ''),
    source: result.source ? String(result.source) : undefined,
    score: result.score,
  };
}

/**
 * Lance une recherche puis regroupe les résultats par `kind`.
 * `limitPerGroup` permet de capper chaque section dans la palette.
 */
export function searchGrouped(
  mini: MiniSearch<SearchDoc>,
  query: string,
  options: { limitPerGroup?: number } = {},
): GroupedHits {
  const empty: GroupedHits = { items: [], episodes: [], guests: [], total: 0 };
  if (!query.trim()) return empty;
  const limit = options.limitPerGroup ?? 5;
  const raw = mini.search(query);
  const all: GroupedHits = { items: [], episodes: [], guests: [], total: raw.length };
  for (const r of raw) {
    const hit = toHit(r);
    if (hit.kind === 'item' && all.items.length < limit) all.items.push(hit);
    else if (hit.kind === 'episode' && all.episodes.length < limit) all.episodes.push(hit);
    else if (hit.kind === 'guest' && all.guests.length < limit) all.guests.push(hit);
  }
  return all;
}
