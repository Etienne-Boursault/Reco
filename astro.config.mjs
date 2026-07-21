import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

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
if (isProd && !siteUrl) {
  throw new Error(
    "[astro.config] SITE_URL est requis en production (build CI/CD). " +
    "Sans valeur, og:url et canonical fuiteraient `https://reco.example`. " +
    "Configure la variable d'environnement avant `astro build`.",
  );
}

export default defineConfig({
  site: siteUrl || 'https://reco.example',
  trailingSlash: 'ignore',
  // Précharge la page cible au survol d'un lien — UX plus vive pour la
  // navigation catalogue → fiche épisode (réseau peu coûteux).
  prefetch: { defaultStrategy: 'hover' },
  integrations: [
    sitemap({
      // Exclut les pages de relecture interne (non destinées au public).
      // Filtre robuste : tolère trailing slash, évite les faux positifs
      // qu'un `includes('/verifier')` pourrait introduire (CR senior C3).
      filter: (page) => {
        // Exclut les pages internes : /verifier (relecture), /reports (queue
        // signalements admin) et /report/* (formulaires individuels, noindex).
        if (page.endsWith('/verifier') || page.endsWith('/verifier/')) return false;
        if (page.endsWith('/reports') || page.endsWith('/reports/')) return false;
        if (page.includes('/report/')) return false;
        // Recherche : page utilitaire (noindex) + endpoint d'index.
        if (page.endsWith('/recherche') || page.endsWith('/recherche/')) return false;
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
