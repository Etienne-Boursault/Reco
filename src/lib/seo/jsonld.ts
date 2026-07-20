/**
 * src/lib/seo/jsonld.ts — Factories JSON-LD (schema.org).
 *
 * Objectif : éviter que chaque page construise son JSON-LD à la main et
 * fournit des helpers typés + un `safeJsonLd()` qui échappe `</script>`
 * (cf. CR senior C2 — XSS via inclusion littérale dans `<script>`).
 *
 * Mapping `recoType → schema.org @type` cohérent avec
 * `src/content.config.ts::recoType` (cf. ADR 0027).
 *
 * Le câblage effectif (appel depuis `Layout.astro` ou les pages) est
 * délégué au Fixer coordination finale — ce module ne fait que fournir les
 * outils.
 */

import { siteConfig } from '../../config/site.js';

/** Type JSON-LD générique. */
export type JsonLd = Record<string, unknown> | Record<string, unknown>[];

/**
 * Mapping `recoType` (collection Astro) → `@type` schema.org.
 * Référence : https://schema.org/CreativeWork sous-types.
 * `as const` pour la lisibilité, `readonly` empêche la mutation accidentelle.
 */
export const RECO_TYPE_TO_SCHEMA: Readonly<Record<string, string>> = {
  film: 'Movie',
  serie: 'TVSeries',
  livre: 'Book',
  bd: 'Book',
  musique: 'MusicRecording',
  album: 'MusicAlbum',
  podcast: 'PodcastSeries',
  jeu: 'VideoGame',
  spectacle: 'Event',
  lieu: 'Place',
  artiste: 'Person',
  video: 'VideoObject',
  autre: 'CreativeWork',
} as const;

/**
 * Sérialise un objet JSON-LD en échappant `</script>` (XSS hardening).
 *
 * Si une donnée d'épisode contenait la chaîne `</script>` (titre, citation,
 * description), `JSON.stringify` la conserverait telle quelle et casserait
 * le `<script type="application/ld+json">` du HTML. L'échappement
 * `<` est neutre côté JSON-LD (parseur Google le décode normalement).
 */
export function safeJsonLd(data: JsonLd): string {
  return JSON.stringify(data).replace(/</g, '\\u003c');
}

// --- Factories ---------------------------------------------------------------

export interface RecoLike {
  /** Type d'œuvre (cf. recoType collection). */
  type: string;
  title: string;
  author?: string;
  url?: string;
  description?: string;
}

/**
 * H11-2 — Mapping `reco.author` (créateur·rice) → propriété schema.org
 * cohérente avec le `@type`. Schema.org refuse `author` sur certains types
 * (Movie, TVSeries veulent `director`; MusicAlbum veut `byArtist`).
 * Garder `author` partout produit du JSON-LD invalide, pénalisant le rich
 * snippet et la confiance Google.
 */
function creatorPropertyFor(schemaType: string): {
  prop: string;
  node: (name: string) => Record<string, unknown>;
} {
  switch (schemaType) {
    case 'Movie':
    case 'TVSeries':
    case 'VideoObject':
      return { prop: 'director', node: (name) => ({ '@type': 'Person', name }) };
    case 'Book':
      return { prop: 'author', node: (name) => ({ '@type': 'Person', name }) };
    case 'MusicAlbum':
    case 'MusicRecording':
      return { prop: 'byArtist', node: (name) => ({ '@type': 'MusicGroup', name }) };
    case 'VideoGame':
      return { prop: 'publisher', node: (name) => ({ '@type': 'Organization', name }) };
    case 'Person':
      // L'œuvre EST une personne ⇒ pas de créateur tiers.
      return { prop: '', node: () => ({}) };
    default:
      // CreativeWork générique : `creator` est la propriété abstraite valide.
      return { prop: 'creator', node: (name) => ({ '@type': 'Person', name }) };
  }
}

/** `Reco` (œuvre recommandée) → CreativeWork-ish typé. */
export function recoToSchema(reco: RecoLike): Record<string, unknown> {
  const schemaType = RECO_TYPE_TO_SCHEMA[reco.type] ?? 'CreativeWork';
  const node: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': schemaType,
    name: reco.title,
  };
  if (reco.author) {
    const { prop, node: makeNode } = creatorPropertyFor(schemaType);
    if (prop) node[prop] = makeNode(reco.author);
  }
  if (reco.url) node.url = reco.url;
  if (reco.description) node.description = reco.description;
  return node;
}

export interface EpisodeLike {
  guid: string;
  title: string;
  description?: string;
  publishedAt?: string;
  url: string;
  podcastName: string;
  podcastUrl?: string;
}

/** Épisode → PodcastEpisode. */
export function episodeToSchema(ep: EpisodeLike): Record<string, unknown> {
  const node: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'PodcastEpisode',
    name: ep.title,
    url: ep.url,
    partOfSeries: {
      '@type': 'PodcastSeries',
      name: ep.podcastName,
      ...(ep.podcastUrl ? { url: ep.podcastUrl } : {}),
    },
  };
  if (ep.description) node.description = ep.description;
  if (ep.publishedAt) node.datePublished = ep.publishedAt;
  return node;
}

export interface SourceLike {
  id: string;
  title: string;
  description?: string;
  url: string;
  rssUrl?: string;
}

/** Source (podcast) → PodcastSeries. */
export function sourceToPodcastSchema(s: SourceLike): Record<string, unknown> {
  const node: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'PodcastSeries',
    name: s.title,
    url: s.url,
    publisher: { '@type': 'Organization', name: siteConfig.siteName },
  };
  if (s.description) node.description = s.description;
  if (s.rssUrl) node.webFeed = s.rssUrl;
  return node;
}
