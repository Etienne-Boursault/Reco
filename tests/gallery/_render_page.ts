/**
 * Harnais partagé pour tester les **pages** de `src/pages` via l'Astro
 * Container API (cf. `tests/components/test_reco_card.test.ts` pour le
 * patron « composant »).
 *
 * Pourquoi un harnais et pas `AstroContainer.create()` nu ?
 * ---------------------------------------------------------
 * Presque toutes les pages calculent des URLs absolues avec
 * `new URL(path, Astro.site)` (canonical, JSON-LD, breadcrumb…). Or le
 * container **ne propage pas** `site` : `createManifest()`
 * (`astro/dist/container/index.js`) reconstruit un manifeste littéral où la
 * clé `site` n'existe pas, et `Pipeline` lit `manifest.site` → `undefined`.
 * Résultat : `new URL('/x', undefined)` lève `TypeError: Invalid URL` avant
 * même que la page ne rende quoi que ce soit.
 *
 * On injecte donc `site` sur le pipeline juste après sa création, via un
 * patch ponctuel de `ContainerPipeline.create`. L'import passe par le chemin
 * de fichier (l'`exports` map d'astro n'expose pas `./dist/container/*`),
 * ce qui résout vers le **même** module que celui utilisé par
 * `astro/container` — donc la même classe.
 *
 * Ce fichier n'est pas une suite de tests (pas de `*.test.ts`) : il est
 * importé par les tests de pages des différents dossiers.
 */
// @ts-expect-error — chemin interne d'astro, non typé par l'exports map.
import { ContainerPipeline } from '../../node_modules/astro/dist/container/pipeline.js';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';

/** Origine utilisée par `astro.config.mjs` quand `SITE_URL` est absent. */
export const TEST_SITE = 'https://reco.example';

/**
 * Crée un container dont le pipeline porte `site`.
 *
 * Le patch est posé JUSTE avant `AstroContainer.create()` et retiré dans le
 * `finally` : `ContainerPipeline` est un module partagé par tout le worker
 * vitest, donc un patch permanent contaminerait les suites des autres
 * dossiers de tests. Ici, la fenêtre d'effet se limite à l'appel.
 *
 * L'affectation est **inconditionnelle** et non pas « seulement si `site` est
 * absent » : `tests/components/_container.ts` installe, lui, un patch
 * permanent qui pose une autre origine (`https://reco.test`). Si ce module
 * est chargé avant celui-ci dans le même worker, un `if (!pipeline.site)`
 * laisserait passer son origine et casserait toutes les assertions d'URL
 * absolue de ce dossier.
 */
async function createContainer(): Promise<InstanceType<typeof AstroContainer>> {
  const original = ContainerPipeline.create;
  ContainerPipeline.create = (options: Record<string, unknown>) => {
    const pipeline = original.call(ContainerPipeline, options);
    pipeline.site = new URL(TEST_SITE);
    return pipeline;
  };
  try {
    return await AstroContainer.create();
  } finally {
    ContainerPipeline.create = original;
  }
}

export interface RenderPageOptions {
  params?: Record<string, string | undefined>;
  props?: Record<string, unknown>;
  /** Chemin (sans origine) servi à `Astro.url` — défaut `/`. */
  path?: string;
}

/**
 * Rend une page Astro complète et renvoie le HTML.
 *
 * `partial: false` force le rendu « page » (doctype + `<html>`), sans quoi
 * le container traite le composant comme un fragment.
 */
export async function renderPage(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Page: any,
  { params, props, path = '/' }: RenderPageOptions = {},
): Promise<string> {
  const container = await createContainer();
  return container.renderToString(Page, {
    params,
    props,
    partial: false,
    request: new Request(new URL(path, TEST_SITE)),
  });
}

/**
 * Texte visible d'une page : `<script>` / `<style>` retirés, balises
 * supprimées, entités HTML courantes décodées, espaces normalisés.
 *
 * Indispensable ici : le compilateur Astro injecte `data-astro-cid-*` et
 * `data-astro-source-file` sur les éléments stylés, et échappe les
 * apostrophes (`l&#39;instant`) — deux détails qui rendraient tout
 * `toContain('<h1>…')` ou `toContain("l'instant")` illisible et fragile.
 */
export function visibleText(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/g, ' ')
    .replace(/<style[\s\S]*?<\/style>/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Comme `renderPage`, mais renvoie la `Response` — nécessaire pour les pages
 * qui peuvent répondre par une redirection (`Astro.redirect`).
 */
export async function renderPageResponse(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Page: any,
  { params, props, path = '/' }: RenderPageOptions = {},
): Promise<Response> {
  const container = await createContainer();
  return container.renderToResponse(Page, {
    params,
    props,
    partial: false,
    request: new Request(new URL(path, TEST_SITE)),
  });
}
