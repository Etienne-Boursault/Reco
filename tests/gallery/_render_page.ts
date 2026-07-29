/**
 * Harnais partagé pour tester les **pages** de `src/pages` via l'Astro
 * Container API (cf. `tests/components/test_reco_card.test.ts` pour le
 * patron « composant »).
 *
 * Ce fichier ne contient plus AUCUN accès aux internes d'Astro. L'injection
 * de `Astro.site` — le seul point qui en réclamait un — vit désormais dans
 * `tests/components/_container.ts`, unique implémentation du dépôt. Avant
 * cette fusion, deux harnais patchaient `ContainerPipeline.create` chacun de
 * son côté, avec deux origines différentes : une montée de version d'Astro
 * les aurait fait tomber ensemble, et celui-ci sans message exploitable.
 * `_container.ts` essaie la voie publique d'abord, ne patche l'interne qu'en
 * repli, et lève une erreur explicite si les deux échouent.
 *
 * Il ne reste ici que ce qui est propre aux PAGES :
 *  - `partial: false` (rendu page complet : doctype + `<html>`, sinon le
 *    container traite le composant comme un fragment) ;
 *  - `params` de route et `path` → `Astro.url` ;
 *  - `visibleText()`, pour écrire des assertions lisibles.
 *
 * Ce n'est pas une suite de tests (pas de suffixe `.test.ts`) : il est
 * importé par les tests de pages des différents dossiers.
 */
import { createSiteContainer, TEST_SITE } from '../components/_container';

export { TEST_SITE };

export interface RenderPageOptions {
  params?: Record<string, string | undefined>;
  props?: Record<string, unknown>;
  /** Chemin (sans origine) servi à `Astro.url` — défaut `/`. */
  path?: string;
}

/** Options de rendu communes aux deux fonctions ci-dessous. */
function renderOptions({ params, props, path = '/' }: RenderPageOptions) {
  return {
    params,
    props,
    partial: false,
    request: new Request(new URL(path, TEST_SITE)),
  };
}

/** Rend une page Astro complète et renvoie le HTML. */
export async function renderPage(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Page: any,
  options: RenderPageOptions = {},
): Promise<string> {
  const container = await createSiteContainer();
  return container.renderToString(Page, renderOptions(options) as never);
}

/**
 * Comme `renderPage`, mais renvoie la `Response` — nécessaire pour les pages
 * qui peuvent répondre par une redirection (`Astro.redirect`).
 */
export async function renderPageResponse(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Page: any,
  options: RenderPageOptions = {},
): Promise<Response> {
  const container = await createSiteContainer();
  return container.renderToResponse(Page, renderOptions(options) as never);
}

/**
 * Texte visible d'une page : `<script>` / `<style>` retirés, balises
 * supprimées, entités HTML courantes décodées, espaces normalisés.
 *
 * Indispensable ici : le compilateur Astro injecte `data-astro-cid-*` et
 * `data-astro-source-file` sur les éléments stylés, et échappe les
 * apostrophes (`l&#39;instant`) — deux détails qui rendraient tout
 * `toContain('<h1>…')` ou `toContain("l'instant")` illisible et fragile.
 *
 * Attention : les attributs disparaissent aussi — un `aria-label` ne sera PAS
 * dans le texte extrait, il faut l'asserter sur le HTML brut.
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
