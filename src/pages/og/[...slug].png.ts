/**
 * Endpoint OG PNG dynamique (résolu au build via `getStaticPaths`).
 *
 * Routes générées :
 *  - /og/default.png                            (carte de repli + homepage)
 *  - /og/<source>.png                           (page source/podcast)
 *  - /og/<source>/episode/<guid>.png            (page épisode)
 *
 * Le rendu se produit pendant `astro build` — aucune dépendance runtime.
 *
 * NB Cache-Control : pas de header émis ici. À build statique, Astro écrit
 * le PNG dans `dist/` et c'est le **serveur** (Netlify / nginx / Cloudflare)
 * qui décide des headers via `_headers` ou équivalent. Émettre un
 * Cache-Control depuis cet endpoint donne l'illusion d'être appliqué alors
 * qu'il est ignoré (cf. CR senior H4 + ADR 0021 §_headers).
 */

import type { APIRoute, GetStaticPaths } from 'astro';
import { getCollection } from 'astro:content';
import { renderOG } from '../../lib/og/renderer.js';
import { TYPE_EMOJI } from '../../lib/og/template.js';

interface PageProps {
  title: string;
  subtitle?: string;
  emoji?: string;
  typeLabel?: string;
  sourceLabel?: string;
  accent?: string;
  bg?: string;
}

/**
 * Slug-safe : garde uniquement [a-z0-9-_/] pour rester valable côté URL.
 * Guarde-fou si un guid contient un jour un caractère exotique
 * (UUID / hex actuels ne posent pas problème). Cohérent avec
 * `src/pages/[source]/episode/[guid].astro` qui consomme le `guid` brut.
 */
function safeSlugSegment(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9_-]/g, '-').replace(/-+/g, '-');
}

export const getStaticPaths: GetStaticPaths = async () => {
  const sources = await getCollection('sources');
  const episodes = await getCollection('episodes');
  const recos = await getCollection('recos');

  const paths: Array<{ params: { slug: string }; props: PageProps }> = [];

  // 1. Carte par défaut (homepage).
  paths.push({
    params: { slug: 'default' },
    props: {
      title: 'Reco',
      subtitle: 'Catalogue de recommandations de podcasts',
      emoji: '🎙️',
      typeLabel: 'Catalogue',
      sourceLabel: 'source-internet.fr',
    },
  });

  // 2. Une carte par source/podcast.
  for (const source of sources) {
    const d = source.data;
    paths.push({
      params: { slug: source.id },
      props: {
        title: d.title,
        subtitle: d.tagline ?? d.description?.slice(0, 80),
        emoji: '🎙️',
        typeLabel: 'Podcast',
        sourceLabel: d.title,
        accent: d.theme?.colors?.accent,
        bg: d.theme?.colors?.bg,
      },
    });
  }

  // 3. Une carte par épisode (qui a au moins une reco validée).
  // Set<string> : on n'a besoin que de `has()` (lookup membership).
  // Typage `ReturnType<typeof Array.prototype.map>` collapsait en `any[]`
  // — cf. CR senior H3.
  const recosBySrcGuid = new Set<string>();
  for (const r of recos) {
    if (r.data.status === 'discarded') continue;
    recosBySrcGuid.add(`${r.data.sourceId.id}::${r.data.episodeGuid}`);
  }
  const sourceById = new Map(sources.map((s) => [s.id, s]));

  for (const ep of episodes) {
    const srcId = ep.data.sourceId.id;
    const key = `${srcId}::${ep.data.guid}`;
    if (!recosBySrcGuid.has(key)) continue;
    const src = sourceById.get(srcId);
    if (!src) continue;
    // P2-P (Fixer coordination Vague 1) : skip les épisodes ayant une
    // miniature YouTube. La page épisode passe déjà `ogImage={thumb}` au
    // Layout, qui a priorité sur `ogSlug`. Générer une carte Satori
    // orpheline gaspillerait ~80 KB × N épisodes (8 MB total) sans aucune
    // utilisation. Cf. ADR 0021 §1 + section « Coordination finale 2026-06-11 ».
    const hasYtThumb = /[?&]v=([\w-]+)/.test(ep.data.youtubeUrl ?? '');
    if (hasYtThumb) continue;
    const epTitle = ep.data.youtubeTitle ?? ep.data.title;
    paths.push({
      params: { slug: `${safeSlugSegment(srcId)}/episode/${safeSlugSegment(ep.data.guid)}` },
      props: {
        title: epTitle,
        subtitle: src.data.title,
        emoji: TYPE_EMOJI.podcast,
        typeLabel: 'Épisode',
        sourceLabel: src.data.title,
        accent: src.data.theme?.colors?.accent,
        bg: src.data.theme?.colors?.bg,
      },
    });
  }

  return paths;
};

export const GET: APIRoute = async ({ props }) => {
  const png = await renderOG(props as PageProps);
  // Note : on retourne un Buffer/Uint8Array — Astro l'écrit tel quel dans dist/.
  // Pas de Cache-Control ici : le mensonge au build statique (cf. H4).
  return new Response(png, {
    headers: { 'Content-Type': 'image/png' },
  });
};
