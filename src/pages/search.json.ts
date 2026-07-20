/**
 * /search.json — Index full-text généré au build.
 *
 * Endpoint statique : Astro l'exécute une fois durant `astro build` et
 * écrit le résultat dans `dist/search.json`. Aucun SSR — compatible
 * `output: 'static'` (kit self-hostable sans adapter Node).
 *
 * Format : `SearchIndexFile` (cf. `src/lib/search/types.ts`).
 *
 * Côté client, `SearchPalette.astro` et `/recherche` `fetch('/search.json')`
 * au premier usage, puis instancient MiniSearch via `createSearchIndex()`.
 *
 * Cf. ADR 0035.
 */

import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { buildSearchIndex } from '../lib/search/build-index';

export const GET: APIRoute = async () => {
  const [sources, episodes, items, mentions] = await Promise.all([
    getCollection('sources'),
    getCollection('episodes'),
    getCollection('items'),
    getCollection('mentions'),
  ]);

  const index = buildSearchIndex({
    sources: sources.map((s) => ({ id: s.data.id, title: s.data.title })),
    episodes: episodes.map((e) => ({
      guid: e.data.guid,
      title: e.data.title,
      sourceId: e.data.sourceId.id,
      guests: e.data.guests,
      number: e.data.number ?? null,
    })),
    items: items.map((it) => ({
      id: it.data.id,
      title: it.data.title,
      types: it.data.types,
      creator: it.data.creator ?? null,
    })),
    mentions: mentions.map((m) => ({
      itemId: m.data.itemId,
      sourceId: m.data.sourceRef.sourceId,
      recommendedBy: m.data.recommendedBy ?? null,
      status: m.data.status,
    })),
  });

  return new Response(JSON.stringify(index), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      // 5 min cache — l'index change à chaque build, on évite le hit cache
      // long sur un asset versionné implicitement.
      'Cache-Control': 'public, max-age=300, must-revalidate',
    },
  });
};
