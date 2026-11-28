/**
 * GET /api/bord — l'audience et les signalements en attente, pour le tableau
 * de bord de venus (tableau de bord, R2 B du 27/11/2026 ; TB-1 C du
 * 28/11/2026, l'audience au centre).
 *
 * L'ACCÈS
 * -------
 * La même clé que `/audience` (`RECO_AUDIENCE_KEY`), comparée par `acces()`
 * en temps constant, mais reçue dans l'en-tête `X-Reco-Cle`, jamais dans
 * l'URL : un appel de machine n'a pas de signet, et l'URL finit dans les
 * journaux. Sans clé valide, ou pour toute autre méthode que GET, la route
 * répond 404, comme si elle n'existait pas.
 *
 * Comme `/audience`, elle n'est pas dans `src/pages/` : `astro.config.mjs`
 * l'injecte seulement avec `RECO_SSR=1`. La mesure ignore `/api/`
 * (`derive.mjs`) : les appels de venus ne comptent pas comme des visites.
 *
 * LA LECTURE
 * ----------
 * `lireAudience`, la même que `/audience`, sur 7 puis 30 jours : deux
 * lectures du disque, au plus une fois toutes les 10 min (plan, § 8). Le
 * résumé est fait par `src/lib/bord/resume.ts`, qui ne laisse sortir d'un
 * signalement ni le nom, ni l'adresse, ni le texte.
 */
import type { APIRoute } from 'astro';

import { acces } from '../lib/audience/acces.mjs';
import { lireAudience } from '../lib/audience/vue';
import { resumerBord } from '../lib/bord/resume';
import { listReports, listSourcesWithReports } from '../lib/reports/storage';
import type { Report } from '../lib/reports/types';

const ENTETES = { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' };

/** Tous les signalements, ou `null` (journalisé) si l'un des dossiers ne se lit pas. */
function lireSignalements(racine: string): Report[] | null {
  try {
    return listSourcesWithReports(racine).flatMap((s) => listReports(s, { cwd: racine }));
  } catch (e) {
    console.error('[api/bord] signalements illisibles :', e);
    return null;
  }
}

export const ALL: APIRoute = ({ request, url, site }) => {
  if (request.method !== 'GET' || !acces(request.headers.get('x-reco-cle')).ouvert) {
    return new Response('Page introuvable', {
      status: 404,
      headers: { ...ENTETES, 'Content-Type': 'text/plain; charset=utf-8' },
    });
  }
  const racine = process.cwd();
  const lire = (nbJours: number) => lireAudience({ racine, filtre: null, nbJours, site, url });
  const resume = resumerBord({
    sept: lire(7),
    trente: lire(30),
    signalements: lireSignalements(racine),
    maintenant: new Date(),
  });
  return new Response(JSON.stringify(resume), {
    status: 200,
    headers: { ...ENTETES, 'Content-Type': 'application/json; charset=utf-8' },
  });
};
