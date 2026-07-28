/**
 * src/pages/api/captcha.ts — Endpoint GET `/api/captcha` : renvoie un défi
 * captcha FRAIS (token signé + question), régénéré à chaque appel.
 *
 * Pourquoi ? La page de signalement (`/[source]/report/[recoId]`) est STATIQUE
 * (pré-rendue) : son token captcha serait figé au build (secret de repli, TTL
 * 4h, jti à usage unique) → les envois casseraient au-delà de 4h ou après un
 * premier POST. Le `ReportForm` récupère donc un token frais ici au chargement
 * (progressive enhancement), signé avec le `REPORTS_SECRET` runtime.
 *
 * Rendu on-demand via le hook `ssrOnDemandRoutes` (astro.config.mjs) quand
 * RECO_SSR=1. Sans le flag (build statique du kit), la route est pré-rendue :
 * elle sert alors un token fixe (démo statique, cohérent avec le reste du kit).
 */

import type { APIRoute } from 'astro';
import { generateChallenge } from '../../lib/reports/captcha.js';

export const GET: APIRoute = () => {
  const challenge = generateChallenge();
  return new Response(JSON.stringify({ token: challenge.token, question: challenge.question }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      // Jamais mis en cache : chaque visiteur doit obtenir son propre défi
      // (jti unique, anti-rejeu). Un cache CDN casserait l'anti-rejeu.
      'Cache-Control': 'no-store, max-age=0',
    },
  });
};
