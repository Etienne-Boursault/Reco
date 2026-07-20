/**
 * src/pages/api/report.ts — Endpoint POST `/api/report` (signalements visiteurs).
 *
 * `prerender = false` : ce handler est dynamique. En `astro dev` il est servi
 * normalement. En build statique (`output: 'static'` sans adapter), Astro
 * émet un warning et le fichier est ignoré au déploiement — c'est attendu
 * et documenté dans ADR 0034 et fork-guide. Pour la prod, ajouter un adapter
 * (`@astrojs/node`, Vercel, Netlify).
 *
 * Toute la logique métier vit dans `src/lib/reports/handler.ts` (testable
 * sans Astro). Ici on se contente :
 *  - de parser le `FormData`,
 *  - d'extraire l'IP via `clientAddress`,
 *  - de calculer `selfOrigin` depuis `request.url`,
 *  - d'appeler le handler et de sérialiser sa réponse.
 */

import type { APIRoute } from 'astro';
import { handleReport } from '../../lib/reports/handler.js';

// P0-2 (Fixer final Phase 2, 2026-06-11) — SSR opt-in :
//
// En `output: 'static'` (config par défaut du kit), Astro 5 REFUSE de
// builder si une page exporte `prerender = false` (NoAdapterInstalled).
// On laisse donc le marqueur en commentaire — l'opérateur fork qui veut
// activer le POST devra :
//   1. installer un adapter (`@astrojs/node`, Vercel, Netlify…),
//   2. basculer `output: 'hybrid'` dans `astro.config.mjs`,
//   3. décommenter la ligne ci-dessous.
//
// Sans cette bascule, le client reçoit 405 et le ReportForm révèle un
// bouton "Envoyer par email" (mailto: pré-rempli, P0-2 ReportForm.astro).
// Cf. fork-guide §reports + §10 (adapter SSR).
//
// SSR opt-in: voir fork-guide §reports
// export const prerender = false;

/**
 * H16-5 — Note sur `prerender = false` :
 *
 * Astro 5 refuse de builder en `output: 'static'` global si une page
 * exporte `prerender = false` (NoAdapterInstalled). On NE PEUT donc PAS
 * mettre le marqueur ici en l'état actuel de la config — il faudrait
 * d'abord passer `output: 'hybrid'` + installer un adapter (cf. fork-guide).
 *
 * Quand un fork bascule SSR, l'opérateur doit ajouter à la main :
 *
 *     export const prerender = false;
 *
 * juste en dessous des imports. C'est intentionnellement *manuel* pour
 * éviter de casser le build static par défaut du kit.
 */

/**
 * Note `prerender` :
 *  - En `output: 'static'` (config par défaut, cf. ADR 0034), ce fichier est
 *    pré-rendu : la sortie statique contient le GET (405) et POST n'est PAS
 *    déployable. C'est attendu pour permettre le build sans adapter.
 *  - En `astro dev` ET en mode SSR/hybrid avec adapter, le POST handler est
 *    appelé dynamiquement et fonctionne pleinement.
 *  - Pour un déploiement prod qui veut accepter les signalements en ligne :
 *    installer `@astrojs/node` (ou Vercel/Netlify) et `output: 'server'`
 *    ou `output: 'hybrid'` + `export const prerender = false;` ICI.
 */

export const POST: APIRoute = async ({ request, clientAddress }) => {
  // FormData → plain object. On garde uniquement les champs scalaires
  // (le honeypot et le captcha sont des `<input>` simples).
  const fd = await request.formData();
  const formData: Record<string, string> = {};
  for (const [k, v] of fd.entries()) {
    if (typeof v === 'string') formData[k] = v;
  }

  const url = new URL(request.url);
  const selfOrigin = `${url.protocol}//${url.host}`;
  const origin = request.headers.get('origin') ?? request.headers.get('referer');

  // `clientAddress` jette en static build ; on protège pour le dev.
  // H16-6 — On NE FAIT confiance à `x-forwarded-for` que si l'IP directe
  // (`clientAddress`) figure dans la liste `TRUSTED_PROXIES` (CSV d'IPs).
  // Sans cette garde, n'importe qui peut forger un header pour contourner
  // le rate-limit.
  let ip = '0.0.0.0';
  let directIp: string | null = null;
  try {
    directIp = clientAddress;
  } catch {
    directIp = null;
  }
  const trustedRaw = process.env.TRUSTED_PROXIES ?? '';
  const trustedProxies = new Set(
    trustedRaw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  );
  const xff = request.headers.get('x-forwarded-for');
  if (directIp && trustedProxies.has(directIp) && xff) {
    // Confiance accordée — on lit l'IP réelle depuis le header.
    ip = xff.split(',')[0].trim() || directIp;
  } else if (directIp) {
    ip = directIp;
  } else {
    // En static build, pas d'IP disponible. Fallback non-trustable mais
    // mieux que rien — le rate-limit deviendra inopérant sur cette voie.
    ip = '0.0.0.0';
  }

  const result = handleReport({ formData, origin, selfOrigin, ip });

  return new Response(JSON.stringify(result.body), {
    status: result.status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
};

/**
 * GET retourne 405 pour signaler clairement que seul POST est supporté.
 * Utile en debug (curl `/api/report` direct dans le navigateur).
 */
export const GET: APIRoute = () =>
  new Response(JSON.stringify({ success: false, error: 'method not allowed' }), {
    status: 405,
    headers: { 'Content-Type': 'application/json; charset=utf-8', Allow: 'POST' },
  });
