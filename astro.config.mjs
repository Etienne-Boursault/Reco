import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Site multi-source de recommandations de podcasts.
// `site` est lu depuis l'environnement pour s'adapter au déploiement
// (Netlify/Vercel/GitHub Pages). Valeur de repli pour le dev local.
export default defineConfig({
  site: process.env.SITE_URL || 'https://reco.example',
  trailingSlash: 'ignore',
  // Précharge la page cible au survol d'un lien — UX plus vive pour la
  // navigation catalogue → fiche épisode (réseau peu coûteux).
  prefetch: { defaultStrategy: 'hover' },
  integrations: [
    sitemap({
      // Exclut les pages de relecture interne (non destinées au public).
      filter: (page) => !page.includes('/verifier'),
    }),
  ],
});
