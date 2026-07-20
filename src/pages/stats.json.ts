/**
 * /stats.json — Sidecar JSON exposé statique du snapshot stats publiques.
 *
 * Pourquoi cet endpoint (M26-17) :
 * - ADR 0047 promet un `DataDownload` JSON-LD pointant vers un export
 *   téléchargeable. Cette route le matérialise — `dist/stats.json` à
 *   `astro build`.
 * - Forks open data : un consommateur tiers peut récupérer les chiffres
 *   sans scraper le HTML.
 * - Pattern sidecar cohérent ADR 0020 (vues matérialisées).
 *
 * Aucun SSR : Astro exécute cet endpoint au build et écrit le résultat
 * dans `dist/stats.json` (compatible `output: 'static'`).
 */
import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { buildStatsSnapshot } from '../lib/stats/aggregator';

// F-CRIT-3 — endpoint statique généré au build (cohérent avec le reste
// du site `output: 'static'`).
export const prerender = true;

/**
 * F-CRIT-4 : determinism du `generatedAt` (cf. `.well-known/reco-registry`).
 */
function deterministicNowIso(env: NodeJS.ProcessEnv = process.env): string {
  const ts = env.RECO_BUILD_TIMESTAMP || env.SOURCE_DATE_EPOCH;
  if (ts) {
    const n = Number(ts);
    if (Number.isFinite(n) && n > 0) {
      const ms = n > 1e12 ? n : n * 1000;
      return new Date(ms).toISOString();
    }
  }
  return new Date().toISOString();
}

export const GET: APIRoute = async () => {
  const [sources, episodes, mentions, items] = await Promise.all([
    getCollection('sources'),
    getCollection('episodes'),
    getCollection('mentions'),
    getCollection('items'),
  ]);

  const snapshot = buildStatsSnapshot({
    options: { generatedAt: deterministicNowIso() },
    sources: sources.map((s) => ({ id: s.id, hosts: s.data.hosts ?? [] })),
    episodes: episodes.map((e) => ({
      sourceId: e.data.sourceId.id,
      date: e.data.date ?? null,
    })),
    mentions: mentions.map((m) => ({
      itemId: m.data.itemId,
      recommendedBy: m.data.recommendedBy ?? null,
      status: m.data.status,
      sourceRef: { sourceId: m.data.sourceRef.sourceId },
    })),
    items: items.map((i) => ({
      id: i.data.id,
      title: i.data.title,
      types: i.data.types,
    })),
  });

  // F-M-1 : Cache-Control aligné sur `/.well-known/reco-registry.json` (1 h).
  // F-M-2 : pas de pretty-print (gain bande passante).
  return new Response(JSON.stringify(snapshot), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'public, max-age=3600, must-revalidate',
    },
  });
};
