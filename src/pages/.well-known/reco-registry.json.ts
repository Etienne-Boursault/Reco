/**
 * /.well-known/reco-registry.json — Self-description machine-readable du fork.
 *
 * Endpoint statique généré au build (compatible `output: 'static'`). Lu par
 * les méta-agrégateurs (ex. source-internet.fr) via `tools/build_meta.py`.
 *
 * Schema : `RegistryDocument` (cf. `src/lib/registry/types.ts`).
 *
 * Conventions :
 *   - Version du générateur : `Reco/<package.json#version>` (R-P1-03).
 *   - Comptage SSOT : `buildRegistry` → `computeGlobalCounts` (X-P0-32).
 *   - `itemsCount` jointé à la source courante (R-P1-01).
 *   - `lastUpdatedAt` = max(episode.date) (H24-3).
 *   - Cache-Control aligné sur le fetcher (1 h, R-P3-12) — informatif côté
 *     hosts statiques (Vercel/Netlify l'ignorent souvent : voir ADR 0045).
 *
 * Cf. ADR 0045.
 */
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { buildRegistry } from '../../lib/registry/generator';
import { parseRegistry } from '../../lib/registry/types';
import pkg from '../../../package.json';

// F-CRIT-3 — endpoint statique : on garantit le pré-rendu au build (Astro 5,
// `output: 'static'` est le défaut mais on l'exprime localement pour qu'un
// éventuel switch en `hybrid`/`server` ne fasse pas régresser).
export const prerender = true;

const GENERATOR = `Reco/${(pkg as { version: string }).version}`;

// 1 h — aligné sur le TTL du fetcher Python (R-P3-12). Override possible via
// l'env `RECO_REGISTRY_CACHE_MAX_AGE` (en secondes).
const CACHE_MAX_AGE = (() => {
  const raw = process.env.RECO_REGISTRY_CACHE_MAX_AGE;
  if (!raw) return 3600;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : 3600;
})();

const CACHE_HEADER = `public, max-age=${CACHE_MAX_AGE}, must-revalidate`;

/**
 * F-CRIT-4 : determinism du `generatedAt`. Si `SOURCE_DATE_EPOCH` ou
 * `RECO_BUILD_TIMESTAMP` est défini, on s'aligne — sinon `now`. Pratique
 * pour la reproductibilité des builds Nix/CI (hash stable).
 */
function deterministicNowIso(env: NodeJS.ProcessEnv = process.env): string {
  const ts = env.RECO_BUILD_TIMESTAMP || env.SOURCE_DATE_EPOCH;
  if (ts) {
    const n = Number(ts);
    if (Number.isFinite(n) && n > 0) {
      // SOURCE_DATE_EPOCH = secondes depuis epoch (Reproducible Builds spec).
      // RECO_BUILD_TIMESTAMP par convention identique pour rester compat.
      const ms = n > 1e12 ? n : n * 1000;
      return new Date(ms).toISOString();
    }
  }
  return new Date().toISOString();
}

function jsonResponse(payload: unknown, status: number = 200): Response {
  // F-M-2 : pas de pretty-print (gain bande passante + diff CI bruyant).
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': CACHE_HEADER,
    },
  });
}

export const GET: APIRoute = async ({ site }) => {
  // `site` est défini par astro.config.mjs (SITE_URL en prod).
  // M24-9 : si non configuré, on retombe sur un domaine IANA-reserved
  // explicite plutôt qu'un `reco.example` ambigu.
  const siteUrl = site?.toString().replace(/\/$/, '') ?? 'https://example.invalid';

  const [sources, episodes, items, mentions] = await Promise.all([
    getCollection('sources'),
    getCollection('episodes'),
    getCollection('items'),
    getCollection('mentions'),
  ]);

  // On expose UN registry par fork. Convention : si plusieurs sources, on
  // sélectionne la 1ʳᵉ (alphabétique) — le kit multi-source reste géré côté
  // méta. Forks single-podcast (le cas standard) sont couverts naturellement.
  const sorted = [...sources].sort((a, b) => a.data.id.localeCompare(b.data.id));
  const source = sorted[0];
  const isMultiSource = sorted.length > 1;

  const now = deterministicNowIso();

  if (!source) {
    // M24-8 : on construit le fallback via buildRegistry pour réutiliser le
    // schema + les defaults (jamais d'inline manuel divergent).
    const fallback = buildRegistry({
      source: { id: 'unknown', title: 'Reco', hosts: [], language: 'fr' },
      episodes: [],
      mentions: [],
      items: [],
      siteUrl,
      generator: GENERATOR,
      generatedAt: now,
      lastUpdatedAt: now,
    });
    return jsonResponse(fallback);
  }

  // R-P1-01 : itemsCount filtré par source → joindre via mentions de la
  // source, puis intersection avec le catalogue items. (Délégué à
  // computeGlobalCounts/uniqueWorksCount via le générateur.)
  const sourceEpisodes = episodes.filter((e) => e.data.sourceId.id === source.data.id);
  const sourceMentions = mentions.filter(
    (m) => m.data.sourceRef.sourceId === source.data.id,
  );

  // M24-10 : langue depuis `source.data.lang` (ADR 0026). Fallback `fr`.
  const sourceData = source.data as { lang?: string };
  const language = sourceData.lang ?? 'fr';

  // F-H-4 : `manifestoUrl` opt-in. Le path est piloté par
  // `RECO_MANIFESTO_PATH` (défaut `/manifeste`) ET on n'expose le lien
  // QUE si la page `src/pages/manifeste.astro` existe (sinon le lien
  // affiché renverrait un 404 — bruit côté agrégateur).
  const manifestoPath = process.env.RECO_MANIFESTO_PATH ?? '/manifeste';
  const manifestoFile = join(
    process.cwd(),
    'src',
    'pages',
    `${manifestoPath.replace(/^\//, '')}.astro`,
  );
  const manifestoUrl = existsSync(manifestoFile)
    ? `${siteUrl}${manifestoPath}`
    : undefined;

  const registry = buildRegistry({
    source: {
      id: source.data.id,
      title: source.data.title,
      tagline: source.data.tagline,
      hosts: source.data.hosts,
      rssUrl: source.data.rssUrl,
      language,
    },
    episodes: sourceEpisodes.map((e) => ({
      sourceId: e.data.sourceId.id,
      date: e.data.date ?? null,
    })),
    mentions: sourceMentions.map((m) => ({
      itemId: m.data.itemId,
      recommendedBy: m.data.recommendedBy ?? null,
      status: m.data.status,
      sourceRef: { sourceId: m.data.sourceRef.sourceId },
    })),
    items: items.map((it) => ({
      id: it.data.id,
      title: it.data.title,
      types: it.data.types ?? [],
    })),
    siteUrl,
    generator: GENERATOR,
    generatedAt: now,
    // H24-3 : `lastUpdatedAt` dérivé de max(episode.date) côté buildRegistry.
    manifestoUrl,
  });

  // F-H-3 : si le fork est multi-source, on peuple `podcasts: []` en plus
  // du premier — l'agrégateur méta peut alors lister TOUS les podcasts.
  // (Le champ `podcast` reste obligatoire pour la rétrocompat schema v1.)
  if (isMultiSource) {
    registry.podcasts = sorted.map((s) => {
      const d = s.data as { lang?: string };
      const rawLang = (d.lang ?? 'fr').trim().toLowerCase();
      const normalizedLang = /^[a-z]{2}/.test(rawLang) ? rawLang.slice(0, 2) : 'fr';
      return {
        title: s.data.title,
        tagline: s.data.tagline,
        rssUrl: s.data.rssUrl,
        hosts: [...(s.data.hosts ?? [])],
        language: normalizedLang,
      };
    });
  }

  // F-CRIT-5 : valider via `parseRegistry` AVANT émission. Si le schema
  // refuse (ex. champ obligatoire manquant suite à un drift), on retourne
  // un 500 explicite plutôt qu'un JSON corrompu qu'un agrégateur tiers
  // afficherait sans broncher.
  try {
    parseRegistry(registry);
  } catch (err) {
    return jsonResponse(
      {
        error: 'registry_validation_failed',
        message: err instanceof Error ? err.message : String(err),
      },
      500,
    );
  }

  return jsonResponse(registry);
};
