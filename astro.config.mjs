import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Site multi-source de recommandations de podcasts.
// `site` sera ajusté selon le déploiement (Netlify/Vercel/GitHub Pages).
export default defineConfig({
  site: 'https://reco.example',
  trailingSlash: 'ignore',
  integrations: [sitemap()],
});
