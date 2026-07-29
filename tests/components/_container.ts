/**
 * Fabrique de conteneur Astro pour les tests de composants qui lisent
 * `Astro.site` (`Layout.astro`, `SourceCatalog.astro`…).
 *
 * Sans `site`, ces composants lèvent `TypeError: Invalid URL` sur
 * `new URL(path, Astro.site)`.
 *
 * Stratégie en deux temps, tranchée À L'EXÉCUTION plutôt qu'en pariant sur
 * une version d'Astro :
 *
 *  1. **Voie publique d'abord.** On crée le conteneur en passant `site` par
 *     les deux options publiques (`astroConfig`, dont le type
 *     `Omit<AstroUserConfig, …>` inclut bien `site`, et `manifest`), puis on
 *     rend une sonde qui affiche `Astro.site`. Si la valeur arrive, on s'en
 *     tient là : aucun accès aux internes.
 *  2. **Repli sur un patch interne**, seulement si la sonde revient vide. En
 *     Astro 5.18 c'est le cas systématique : `AstroContainer.create()`
 *     déstructure `{streaming, manifest, renderers, resolve}` — l'option
 *     `astroConfig` est purement ignorée — et son `createManifest()`
 *     reconstruit un manifeste clé par clé sans jamais recopier `site`. On
 *     injecte donc `site` là où le pipeline le lit (`manifest.site`, dans le
 *     constructeur de `Pipeline`).
 *
 * Le module interne est chargé **paresseusement** et par chemin de fichier
 * (la carte `exports` du paquet ne publie pas ce sous-chemin). Conséquence
 * voulue : si une version future d'Astro branche enfin `astroConfig`,
 * l'étape 1 suffit et ce fichier ne touche plus jamais aux internes — même
 * si Astro les a déplacés entre-temps. Et si aucune des deux voies ne
 * fonctionne, on lève une erreur explicite qui dit quoi ré-adapter.
 */
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import SiteProbe from './_site_probe.astro';

/** Origine utilisée comme `Astro.site` dans les tests. */
export const TEST_SITE = 'https://reco.test';

/** Voie retenue pour injecter `site`. */
export type VoieSite = 'publique' | 'patch-interne';

/**
 * Forme normalisée attendue de `Astro.site`. `Astro.site` est un objet `URL` :
 * sa sérialisation ajoute la barre oblique finale (`https://reco.test/`). On
 * compare donc à la forme normalisée, pas à la constante brute.
 */
const SITE_NORMALISE = new URL(TEST_SITE).toString();

/** Chemin de fichier vers l'interne d'Astro — non publié par `exports`. */
const PIPELINE_INTERNE = '../../node_modules/astro/dist/container/pipeline.js';

/** Options publiques transmises à chaque création de conteneur. */
const OPTIONS_PUBLIQUES = {
  astroConfig: { site: TEST_SITE },
  manifest: { site: TEST_SITE },
};

type Conteneur = Awaited<ReturnType<typeof AstroContainer.create>>;

async function creerConteneur(): Promise<Conteneur> {
  return AstroContainer.create(OPTIONS_PUBLIQUES as never);
}

/** `Astro.site` tel que le voit un composant rendu par ce conteneur. */
async function siteVuParUnComposant(container: Conteneur): Promise<string> {
  try {
    const html = await container.renderToString(SiteProbe as never, {});
    return html.match(/data-site="([^"]*)"/)?.[1] ?? '';
  } catch {
    // Selon les versions, un `site` absent peut faire lever la sonde.
    return '';
  }
}

/** Installe le patch interne (idempotent). Lève si l'interne a bougé. */
async function installerPatchInterne(): Promise<void> {
  let module: Record<string, unknown>;
  try {
    // Import dynamique à specifier LITTÉRAL : il doit passer par la
    // résolution de Vite, seule façon d'obtenir la MÊME instance de module
    // que celle utilisée par `astro/container`. Un specifier calculé (ou un
    // `@vite-ignore`) retomberait sur le chargeur ESM de Node et créerait une
    // seconde instance — le patch serait alors posé sur une copie inerte.
    module = (await import('../../node_modules/astro/dist/container/pipeline.js')) as Record<
      string,
      unknown
    >;
  } catch (cause) {
    throw new Error(
      '[tests/_container] Astro ne transmet pas `site` par les options publiques, ' +
        `et le module interne de repli (${PIPELINE_INTERNE}) est introuvable. ` +
        "Ré-adapter l'injection de `site` pour cette version d'Astro.",
      { cause },
    );
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const CP = module.ContainerPipeline as any;
  if (typeof CP?.create !== 'function') {
    throw new Error(
      "[tests/_container] L'API interne d'Astro a changé : " +
        `ContainerPipeline.create est introuvable dans ${PIPELINE_INTERNE}. ` +
        'Ré-adapter l’injection de `site`.',
    );
  }
  if (CP.__recoSitePatched) return;

  const original = CP.create.bind(CP);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  CP.create = (options: any) => {
    if (options?.manifest && !options.manifest.site) options.manifest.site = TEST_SITE;
    return original(options);
  };
  CP.__recoSitePatched = true;
}

/** Résolue une seule fois par worker : la voie retenue pour injecter `site`. */
let voie: Promise<VoieSite> | null = null;

function resoudreVoie(): Promise<VoieSite> {
  voie ??= (async () => {
    if ((await siteVuParUnComposant(await creerConteneur())) === SITE_NORMALISE) {
      return 'publique';
    }
    await installerPatchInterne();
    if ((await siteVuParUnComposant(await creerConteneur())) !== SITE_NORMALISE) {
      throw new Error(
        '[tests/_container] `Astro.site` reste indéfini malgré le patch interne. ' +
          'Le pipeline de conteneur d’Astro ne lit plus `manifest.site` — ' +
          'ré-adapter l’injection.',
      );
    }
    return 'patch-interne';
  })();
  return voie;
}

/** Conteneur prêt à rendre un composant qui dépend de `Astro.site`. */
export async function createSiteContainer(): Promise<Conteneur> {
  await resoudreVoie();
  return creerConteneur();
}

/** Voie effectivement retenue — exposée pour être vérifiée par un test. */
export async function voieUtilisee(): Promise<VoieSite> {
  return resoudreVoie();
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
