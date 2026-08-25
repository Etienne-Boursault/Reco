import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import node from '@astrojs/node';

/**
 * Site multi-source de recommandations de podcasts.
 *
 * `site` est lu depuis l'environnement pour s'adapter au déploiement
 * (Netlify / Vercel / GitHub Pages). En **production**, l'absence de
 * `SITE_URL` est une faute critique : tous les URLs absolus (`og:url`,
 * `canonical`, `sitemap`) tomberaient sur `reco.example`. On `throw`
 * dans ce cas pour faire échouer le build (CR senior H10).
 */
const isProd = process.env.NODE_ENV === 'production' || process.env.CI === 'true';
const siteUrl = process.env.SITE_URL;
// SSR opt-in : RECO_SSR=1 active l'adaptateur Node (déploiement). Sans le flag
// (CI, tests, build statique par défaut) : aucun adaptateur, tout est pré-rendu.
const wantSSR = process.env.RECO_SSR === '1';
if (isProd && !siteUrl) {
  throw new Error(
    "[astro.config] SITE_URL est requis en production (build CI/CD). " +
    "Sans valeur, og:url et canonical fuiteraient `https://reco.example`. " +
    "Configure la variable d'environnement avant `astro build`.",
  );
}

/**
 * Force certaines routes en on-demand (`prerender=false`) quand RECO_SSR=1.
 *
 * Astro n'honore PAS un `export const prerender` *calculé* (il lui faut un
 * littéral) : les endpoints restaient donc pré-rendus, et leur fichier statique
 * (`dist/client/api/report` = le 405 figé) court-circuitait le handler
 * dynamique — le POST ne l'atteignait jamais. Ce hook fixe `route.prerender`
 * de façon fiable au build. Sans RECO_SSR=1 (CI / build statique du kit),
 * c'est un no-op → tout reste pré-rendu, aucun adaptateur requis.
 */
function ssrOnDemandRoutes() {
  // `audience` : le tableau de bord lit les mesures du jour. Pré-rendu, il
  // serait figé à la date du dernier déploiement.
  const ONDEMAND = ['api/report', 'api/click', 'api/captcha', 'audience'];
  return {
    name: 'reco-ssr-ondemand-routes',
    hooks: {
      'astro:route:setup': ({ route }) => {
        if (process.env.RECO_SSR !== '1') return;
        const comp = route.component ?? '';
        if (ONDEMAND.some((p) => comp.includes(p))) {
          route.prerender = false;
        }
      },
    },
  };
}

export default defineConfig({
  site: siteUrl || 'https://reco.example',
  // Avec RECO_SSR=1 : adaptateur Node → les routes forcées en `prerender=false`
  // (cf. ssrOnDemandRoutes) deviennent dynamiques. Sinon aucun adaptateur.
  //
  // Mode `middleware` et NON `standalone` : en standalone, Astro démarre son
  // propre serveur HTTP et rien ne peut s'insérer devant. Or `@astrojs/node`
  // ne compresse pas, et l'hébergement n'offre aucun réglage pour le faire —
  // le site partait donc à 2599 Ko au lieu de 199 (mesuré le 2026-08-16).
  // En `middleware`, l'entrée exporte un gestionnaire que `server.mjs` monte
  // derrière sa propre couche de compression. C'est `server.mjs` que lance
  // `npm start`, et donc l'hébergeur.
  ...(wantSSR ? { adapter: node({ mode: 'middleware' }) } : {}),
  trailingSlash: 'ignore',
  // Astro 7 bascule `compressHTML` sur `'jsx'` par défaut : la compression
  // devient JSX-aware et SUPPRIME les blancs entre un texte et une balise
  // inline quand ils ne tiennent qu'à un retour à la ligne du template.
  // Mesuré sur ce site : ça collait le texte sur 1 123 pages sur 2 661
  // (« publiée sur<a>source-internet.fr</a>et agrège » → « publiée
  // sursource-internet.fret agrège », « dans leManifeste éthique »). Ni le
  // build, ni vitest, ni l'a11y, ni le contraste ne voient les espaces : le
  // défaut se serait déployé sans qu'aucune porte ne sonne. On garde donc le
  // comportement HTML-aware d'Astro 5, qui préserve ces espaces.
  compressHTML: true,
  // Précharge la page cible au survol d'un lien — UX plus vive pour la
  // navigation catalogue → fiche épisode (réseau peu coûteux).
  prefetch: { defaultStrategy: 'hover' },
  integrations: [
    ssrOnDemandRoutes(),
    sitemap({
      // Exclut les pages de relecture interne (non destinées au public).
      // Filtre robuste : tolère trailing slash, évite les faux positifs
      // qu'un `includes('/verifier')` pourrait introduire (CR senior C3).
      filter: (page) => {
        // Exclut les pages internes : /verifier (relecture), /reports (queue
        // signalements admin) et /report/* (formulaires individuels, noindex).
        if (page.endsWith('/verifier') || page.endsWith('/verifier/')) return false;
        if (page.endsWith('/reports') || page.endsWith('/reports/')) return false;
        // Sommaire interne des galeries : les pages qu'il liste sont
        // publiques et indexees, mais le sommaire lui-meme n'a rien a faire
        // dans les resultats de recherche — il sert a la relecture.
        if (page.endsWith('/galeries') || page.endsWith('/galeries/')) return false;
        if (page.includes('/report/')) return false;
        // Fragments chargés à la demande : ce sont des MORCEAUX de page, sans
        // `<html>`, `<head>` ni titre. Indexés, ils entreraient en concurrence
        // avec la page complète qu'ils dupliquent, et offriraient au visiteur
        // arrivant du moteur un document sans mise en forme ni navigation.
        // La page complète (`/recos`) reste au sitemap : c'est elle la version
        // publique de cette vue.
        if (page.endsWith('/recos-fragment') || page.endsWith('/recos-fragment/')) return false;
        // Recherche : page utilitaire (noindex) + endpoint d'index.
        if (page.endsWith('/recherche') || page.endsWith('/recherche/')) return false;
        // Tableau de bord interne : protégé par une clé, jamais à indexer.
        if (page.endsWith('/audience') || page.endsWith('/audience/')) return false;
        if (page.endsWith('/search.json')) return false;
        // F-M-10 : endpoints JSON (sidecars / registry) — pas des pages
        // HTML, on évite de polluer le sitemap (qui doit cibler des URLs
        // crawlables HTML).
        if (page.endsWith('/reco-registry.json')) return false;
        if (page.endsWith('/stats.json')) return false;
        // F-CRIT-1 — méta-site : `/meta/*` ne doit apparaître au sitemap
        // QUE quand META_MODE=1 est explicitement activé pour ce build
        // (cas du fork méta `source-internet.fr`). Sur un fork standard,
        // les pages sont déjà absentes (getStaticPaths vide), mais on
        // double-protège ici contre une régression future où `/meta/*`
        // pourrait être pré-rendue par erreur.
        if (process.env.META_MODE !== '1') {
          if (page.includes('/meta/') || page.endsWith('/meta')) return false;
        }
        return true;
      },
      // Métadonnées par-défaut. `lastmod` est posé à la date du build
      // (pas d'horloge par-URL ici — on n'a pas de mtime côté Astro). Une
      // bascule serait un `serialize:` lisant `episode.data.publishedAt`.
      lastmod: new Date(),
      changefreq: 'weekly',
      priority: 0.7,
      // @astrojs/sitemap split à 45 000 URLs (la limite RFC est 50 000).
      // Configurable via `entryLimit` si la collection explose.
      entryLimit: 45_000,
    }),
  ],
});
