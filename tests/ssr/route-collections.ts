/**
 * Route de TEST : compte les entrées de chaque collection, lues à l'exécution.
 *
 * Elle n'existe que dans un build `RECO_SSR=1 RECO_TEST_ROUTES=1`
 * (`astro.config.mjs` l'injecte alors en `/__tests/collections`, rendue à la
 * demande). La production ne pose jamais `RECO_TEST_ROUTES` : la route n'y est
 * pas construite. Elle vit dans `tests/` pour la même raison.
 *
 * Elle répond à une question de la V2 : `getCollection` marche-t-il pendant une
 * requête, sous l'adaptateur `@astrojs/node`, ou seulement au build ? La
 * réponse décide de la forme du repli « embarqué » (ADR 0058) — cf.
 * `tests/ssr/verifier-collections-ssr.mjs`.
 */
import type { APIRoute } from 'astro';

import { lecteur } from '../../src/lib/catalog/reader';

export const prerender = false;

const COLLECTIONS = ['sources', 'episodes', 'recos', 'items', 'mentions'] as const;

export const GET: APIRoute = async (contexte) => {
  const catalogue = lecteur(contexte);
  const comptes: Record<string, number> = {};
  for (const nom of COLLECTIONS) comptes[nom] = (await catalogue.collection(nom)).length;
  return new Response(JSON.stringify(comptes), {
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });
};
