/**
 * Endpoint OG PNG dynamique (résolu au build via `getStaticPaths`).
 *
 * Routes générées :
 *  - /og/default.png                            (carte de repli)
 *  - /og/<source>.png                           (source, accueil mono-source)
 *  - /og/<source>/episode/<guid>.png            (épisode avec ≥ 1 reco)
 *  - /og/<source>/galerie/<slug>.png            (galerie par type)
 *  - /og/<source>/oeuvre/<itemId>.png           (œuvre assez citée)
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
import { renderOG, type OGCarte } from '../../lib/og/renderer.js';
import { cartesDuSite } from '../../lib/og/cartes.js';

/**
 * Les cartes « Étiquette » (audit d'interface du 2026-10-07) : accueil,
 * sources, épisodes, galeries et fiches d'œuvre. Le choix des cartes et leurs
 * chiffres vivent dans `lib/og/cartes.ts` ; ici, seulement la lecture des
 * collections et leur mise à plat.
 */
export const getStaticPaths: GetStaticPaths = async () => {
  const [sources, episodes, recos, items, mentions] = await Promise.all([
    getCollection('sources'),
    getCollection('episodes'),
    getCollection('recos'),
    getCollection('items'),
    getCollection('mentions'),
  ]);

  const cartes = cartesDuSite({
    sources: sources.map((s) => ({
      id: s.id,
      title: s.data.title,
      tagline: s.data.tagline,
      accent: s.data.theme?.colors?.accent,
      bg: s.data.theme?.colors?.bg,
    })),
    episodes: episodes.map((e) => ({
      guid: e.data.guid,
      sourceId: e.data.sourceId.id,
      title: e.data.title,
      number: e.data.number,
      season: e.data.season,
    })),
    recos: recos.map((r) => ({
      id: r.data.id,
      sourceId: r.data.sourceId.id,
      episodeGuid: r.data.episodeGuid,
      status: r.data.status,
      title: r.data.title,
      kind: r.data.kind,
      guestWork: r.data.guestWork,
      timestamp: r.data.timestamp,
    })),
    // L'identifiant d'entrée d'un item est son chemin, `<source>/<id>` : c'est
    // la seule trace de sa source (cf. la page œuvre, qui filtre de même).
    items: items.map((it) => ({
      id: it.data.id,
      sourceId: it.id.split('/')[0] ?? '',
      title: it.data.title,
      types: it.data.types,
      creator: it.data.creator ?? null,
    })),
    mentions: mentions.map((m) => ({
      id: m.data.id,
      itemId: m.data.itemId,
      sourceRef: {
        sourceId: m.data.sourceRef.sourceId,
        episodeGuid: m.data.sourceRef.episodeGuid ?? null,
        timestamp: m.data.sourceRef.timestamp ?? null,
        transcriptSource: m.data.sourceRef.transcriptSource ?? null,
      },
      recommendedBy: m.data.recommendedBy ?? null,
      kind: m.data.kind,
      guestWork: m.data.guestWork ?? null,
      status: m.data.status,
    })),
  });

  return cartes.map(({ slug, carte }) => ({ params: { slug }, props: carte }));
};

export const GET: APIRoute = async ({ props }) => {
  const png = await renderOG(props as OGCarte);
  // Note : on retourne un Buffer/Uint8Array — Astro l'écrit tel quel dans dist/.
  // Pas de Cache-Control ici : le mensonge au build statique (cf. H4).
  // TS 5.7 a rendu `Uint8Array` generique sur son buffer ; `BodyInit`
  // n'accepte que la variante `ArrayBuffer`. Le PNG rendu par resvg en est
  // bien une — l'ecart est purement nominal, aucun changement d'execution.
  return new Response(png as Uint8Array<ArrayBuffer>, {
    headers: { 'Content-Type': 'image/png' },
  });
};
