/**
 * Fabrique de conteneur Astro pour les tests de composants qui lisent
 * `Astro.site` (Layout.astro, SourceCatalog.astro…).
 *
 * Pourquoi ce helper ? L'Astro Container API (5.18) n'expose AUCUN moyen
 * public de définir `site` :
 *  - `AstroContainer.create({ astroConfig })` ignore l'option (le code
 *    déstructure `{ streaming, manifest, renderers, resolve }` puis valide
 *    `ASTRO_CONFIG_DEFAULTS`, pas la config utilisateur) ;
 *  - `createManifest()` reconstruit un manifeste neuf clé par clé et n'y
 *    recopie jamais `site`.
 *
 * Sans `site`, tout composant qui fait `new URL(path, Astro.site)` lève
 * « TypeError: Invalid URL ». On injecte donc `site` dans le manifeste au
 * moment exact où le pipeline le consomme (`Pipeline` lit `manifest.site`
 * dans son constructeur). Le patch est posé une seule fois par module.
 *
 * L'import passe par le chemin de fichier (et non par le specifier `astro/…`)
 * parce que la carte `exports` du paquet ne publie pas ce sous-chemin.
 */
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — internals Astro, non typés à l'export
import { ContainerPipeline } from '../../node_modules/astro/dist/container/pipeline.js';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';

/** Origine utilisée comme `Astro.site` dans les tests. */
export const TEST_SITE = 'https://reco.test';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CP = ContainerPipeline as any;
if (!CP.__recoSitePatched) {
  const original = CP.create.bind(CP);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  CP.create = (options: any) => {
    if (options?.manifest && !options.manifest.site) options.manifest.site = TEST_SITE;
    return original(options);
  };
  CP.__recoSitePatched = true;
}

/** Conteneur prêt à rendre un composant qui dépend de `Astro.site`. */
export async function createSiteContainer(): Promise<
  Awaited<ReturnType<typeof AstroContainer.create>>
> {
  return AstroContainer.create();
}

/** Rend un composant avec `Astro.site` défini. */
export async function renderWithSite(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Component: any,
  options: {
    props?: Record<string, unknown>;
    slots?: Record<string, unknown>;
    request?: Request;
  } = {},
): Promise<string> {
  const container = await createSiteContainer();
  return container.renderToString(Component, options as never);
}
