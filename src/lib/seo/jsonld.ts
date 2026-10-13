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
 *
 * ⚠️ N'utiliser ici QUE des types sans champ obligatoire côté Google.
 *
 * On ne dispose que de quatre informations par œuvre : nom, créateur, URL et
 * description. Un type schema.org qui en exige davantage produit un balisage
 * incomplet, que la Search Console remonte en « problème critique » et qui
 * empêche la page de figurer dans les résultats enrichis. Trois mappings sont
 * tombés dans ce piège avant d'être corrigés le 2026-08-29 :
 *
 *   - `spectacle: 'Event'`  → exige `startDate` + `location`. Un spectacle
 *     recommandé dans un podcast est une œuvre, pas une représentation datée :
 *     il n'a ni date ni lieu, et ne peut pas en avoir. 182 pages signalées.
 *   - `video: 'VideoObject'` → exige `thumbnailUrl` + `uploadDate`. On ne
 *     référence pas le fichier vidéo, seulement l'œuvre. 121 pages.
 *   - `application: 'SoftwareApplication'` → exige `offers` ou
 *     `aggregateRating`. On ne connaît ni prix ni note. 16 pages.
 *
 * Les sous-types de CreativeWork conservés ci-dessous (Movie, Book, TVSeries,
 * MusicAlbum…) n'imposent rien : ils précisent la nature de l'œuvre sans
 * risque. Avant d'ajouter une entrée, vérifier la page « Structured data »
 * du type sur developers.google.com/search/docs/appearance/structured-data.
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
  spectacle: 'CreativeWork',
  lieu: 'Place',
  artiste: 'Person',
  video: 'CreativeWork',
  chaine: 'CreativeWorkSeries',
  application: 'CreativeWork',
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
} | null {
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
      // L'œuvre EST une personne ⇒ pas de créateur tiers. On renvoie `null`
      // plutôt qu'un `{ prop: '', node: () => ({}) }` : le sentinel vide
      // obligeait l'appelant à tester `prop` et laissait un `node` que rien ne
      // pouvait jamais appeler (code mort).
      return null;
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
    const creator = creatorPropertyFor(schemaType);
    if (creator) node[creator.prop] = creator.node(reco.author);
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
  /** Page du site consacrée au podcast (repli si la page officielle manque). */
  url: string;
  /** Page OFFICIELLE du podcast (plateforme d'écoute, site de l'émission). */
  officialUrl?: string;
  /** Autres présences officielles du podcast (chaîne YouTube…). */
  sameAs?: readonly string[];
  rssUrl?: string;
}

/**
 * Source (podcast) → PodcastSeries.
 *
 * Le podcast n'est pas celui du site : son `url` est sa page officielle quand
 * on la connaît, et aucun `publisher` n'est déclaré. Jusqu'au 2026-10-13,
 * l'accueil annonçait « Un Bon Moment », à l'adresse unebonnere.co, publié
 * par Une Bonne Reco — de quoi faire prendre le site pour la page officielle
 * de l'émission.
 */
export function sourceToPodcastSchema(s: SourceLike): Record<string, unknown> {
  const node: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'PodcastSeries',
    name: s.title,
    url: s.officialUrl ?? s.url,
  };
  if (s.description) node.description = s.description;
  if (s.rssUrl) node.webFeed = s.rssUrl;
  if (s.sameAs?.length) node.sameAs = [...s.sameAs];
  return node;
}

/**
 * Le site lui-même → WebSite, pour la page d'accueil.
 *
 * C'est ce bloc que Google lit pour nommer le site dans ses résultats et
 * reconnaître une recherche de son nom (`name` + `alternateName`). `sameAs`
 * relie la marque à ses comptes officiels. `about` dit de quel podcast il
 * parle, sans s'en dire l'auteur.
 */
export function siteToWebsiteSchema(url: string, about?: string): Record<string, unknown> {
  const node: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: siteConfig.siteName,
    url,
    description: siteConfig.baseline,
    inLanguage: 'fr-FR',
  };
  if (siteConfig.alternateNames?.length) node.alternateName = [...siteConfig.alternateNames];
  const sameAs = (siteConfig.socials ?? []).map((s) => s.url);
  if (sameAs.length) node.sameAs = sameAs;
  if (about) node.about = { '@type': 'PodcastSeries', name: about };
  return node;
}
