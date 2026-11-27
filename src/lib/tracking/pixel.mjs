/**
 * Le GIF 1×1 transparent du pixel de repli de `/api/click` (requête GET, sans
 * JavaScript).
 *
 * Partagé par `src/pages/api/click.ts` et par `src/server/serveur.mjs`, qui
 * rend le même GIF à une adresse exclue (R-14, 27/11/2026) : un 204 casserait
 * l'`<img>` de repli (constat du tour 1 de revue, PR #224). Fichier `.mjs`
 * parce que `serveur.mjs` tourne en Node pur, sans passer par Astro.
 */

/** 43 octets encodés en base64 : en-tête, LZW, fin. */
export const PIXEL_GIF_BASE64 = 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

export const PIXEL_GIF = Buffer.from(PIXEL_GIF_BASE64, 'base64');

/** Les en-têtes de la réponse : taille sur le fil, jamais mis en cache. */
export const ENTETES_PIXEL = {
  'Content-Type': 'image/gif',
  'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
  'Content-Length': String(PIXEL_GIF.length),
};
