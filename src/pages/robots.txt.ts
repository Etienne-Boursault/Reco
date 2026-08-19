/**
 * robots.txt généré dynamiquement (build-time).
 *
 * Lit `Astro.site` pour pointer vers le sitemap absolu, ce qui évite le
 * hardcode `https://reco.example` du fichier statique précédent. La
 * directive `Disallow: /*\/verifier` est conservée : les pages de
 * relecture interne ne sont pas pour Google.
 *
 * Note : pas de `Allow: /` — par défaut robots.txt **autorise** tout ce
 * qui n'est pas explicitement bloqué. La ligne `Allow: /` était redondante
 * et créait un faux signal (cf. CR senior C4).
 */

import type { APIRoute } from 'astro';

export const GET: APIRoute = ({ site }) => {
  const base = (site ?? new URL('http://localhost/')).toString().replace(/\/$/, '');
  const body = [
    'User-agent: *',
    'Disallow: /*/verifier',
    'Disallow: /*/reports',
    // Sommaire interne des galeries. Les pages qu'il liste restent
    // parfaitement indexables : c'est le sommaire, outil de relecture, qu'on
    // garde hors des resultats.
    'Disallow: /*/galeries',
    'Disallow: /*/report/',
    'Disallow: /api/',
    'Disallow: /search.json',
    'Disallow: /recherche',
    '',
    `Sitemap: ${base}/sitemap-index.xml`,
    '',
  ].join('\n');
  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
