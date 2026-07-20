/**
 * src/lib/search/build-index.ts — Construit la liste plate de documents
 * indexables à partir des collections Astro.
 *
 * Pures fonctions : on passe les collections déjà chargées (sources,
 * episodes, items, mentions) et on obtient `SearchDoc[]`. Aucune I/O ici,
 * 100 % testable.
 *
 * Trois `kinds` :
 *   - `item`    : œuvre canonique  → /<source>/oeuvre/<itemId>
 *   - `episode` : épisode          → /<source>/episode/<guid>
 *   - `guest`   : invité           → /<source>/invite/<slug>
 *
 * Côté client, MiniSearch boost le `title` et donne un poids moindre à
 * `subtitle`/`text` (cf. `src/lib/search/client.ts`).
 */

import { slugify } from '../gallery/slug';
import { SEARCH_INDEX_VERSION, type SearchDoc, type SearchIndexFile } from './types';

// --- Entrées (formes minimales — duck-typing pour rester testable) ---------

export interface SourceLike {
  id: string;
  title: string;
}

export interface EpisodeLike {
  guid: string;
  title: string;
  sourceId: string;
  guests?: readonly string[];
  number?: number | null;
}

export interface ItemLike {
  id: string;
  title: string;
  types: readonly string[];
  creator?: string | null;
  /** Source de rattachement, déduite via mentions. */
  source?: string;
}

export interface MentionLike {
  itemId: string;
  sourceId: string;
  recommendedBy?: string | null;
  status?: 'draft' | 'validated' | 'discarded';
}

// --- Builders --------------------------------------------------------------

/** Construit un doc `item` à partir d'un item + sa source rattachée. */
export function itemToDoc(item: ItemLike, sourceId: string): SearchDoc {
  return {
    id: `item:${sourceId}:${item.id}`,
    kind: 'item',
    title: item.title,
    subtitle: item.creator ?? undefined,
    text: item.types.join(' '),
    source: sourceId,
    url: `/${sourceId}/oeuvre/${item.id}`,
  };
}

/** Construit un doc `episode`. */
export function episodeToDoc(ep: EpisodeLike): SearchDoc {
  const guests = ep.guests?.length ? ep.guests.join(' ') : undefined;
  return {
    id: `episode:${ep.sourceId}:${ep.guid}`,
    kind: 'episode',
    title: ep.title,
    subtitle: ep.number != null ? `Épisode ${ep.number}` : undefined,
    text: guests,
    source: ep.sourceId,
    url: `/${ep.sourceId}/episode/${ep.guid}`,
  };
}

/** Construit un doc `guest` (un par paire source+slug, déduit des épisodes). */
export function guestToDoc(name: string, sourceId: string): SearchDoc | null {
  const slug = slugify(name);
  if (!slug) return null;
  return {
    id: `guest:${sourceId}:${slug}`,
    kind: 'guest',
    title: name,
    source: sourceId,
    url: `/${sourceId}/invite/${slug}`,
  };
}

/**
 * Construit l'index complet à partir des collections Astro.
 * Filtre les mentions/items `discarded` et ne garde qu'une entrée invité
 * par (source, slug).
 */
export function buildSearchIndex(input: {
  sources: readonly SourceLike[];
  episodes: readonly EpisodeLike[];
  items: readonly ItemLike[];
  mentions: readonly MentionLike[];
  generatedAt?: string;
}): SearchIndexFile {
  const sourceIds = new Set(input.sources.map((s) => s.id));

  // Items : on déduit la source par les mentions (un item peut être mentionné
  // dans plusieurs sources → un doc par paire).
  const itemBySourcePairs = new Map<string, ItemLike>();
  const itemById = new Map(input.items.map((it) => [it.id, it] as const));
  for (const m of input.mentions) {
    if (m.status === 'discarded') continue;
    if (!sourceIds.has(m.sourceId)) continue;
    const it = itemById.get(m.itemId);
    if (!it) continue;
    itemBySourcePairs.set(`${m.sourceId}|${m.itemId}`, it);
  }
  const itemDocs: SearchDoc[] = [];
  for (const key of itemBySourcePairs.keys()) {
    const [sourceId, itemId] = key.split('|');
    const it = itemById.get(itemId)!;
    itemDocs.push(itemToDoc(it, sourceId));
  }

  // Épisodes : on garde ceux dont la source est connue.
  const episodeDocs: SearchDoc[] = [];
  const guestPairs = new Set<string>();
  const guestDocs: SearchDoc[] = [];
  for (const ep of input.episodes) {
    if (!sourceIds.has(ep.sourceId)) continue;
    episodeDocs.push(episodeToDoc(ep));
    for (const g of ep.guests ?? []) {
      const slug = slugify(g);
      if (!slug) continue;
      const key = `${ep.sourceId}|${slug}`;
      if (guestPairs.has(key)) continue;
      guestPairs.add(key);
      const d = guestToDoc(g, ep.sourceId);
      if (d) guestDocs.push(d);
    }
  }

  const docs: SearchDoc[] = [...itemDocs, ...episodeDocs, ...guestDocs];

  return {
    version: SEARCH_INDEX_VERSION,
    generatedAt: input.generatedAt ?? new Date().toISOString(),
    count: docs.length,
    docs,
  };
}
