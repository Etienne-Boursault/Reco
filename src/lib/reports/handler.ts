/**
 * src/lib/reports/handler.ts — Logique métier de l'endpoint /api/report.
 *
 * Séparé du fichier `src/pages/api/report.ts` pour être testable sans avoir
 * à lancer Astro. Le shim côté pages ne fait qu'adapter `APIContext` → ce
 * handler.
 *
 * Couches d'acceptation (court-circuit dès le premier rejet) :
 *  1. Origin/Referer header (CSRF).
 *  2. Honeypot rempli ⇒ 204 silencieux (le bot croit avoir réussi).
 *  3. Validation Zod du payload (`reportPayloadSchema`).
 *  4. Captcha math (HMAC + réponse).
 *  5. Rate-limit IP.
 *  6. Écriture atomique du JSON.
 *
 * Codes de retour : 200 (ok), 204 (honeypot silencieux), 400 (validation),
 * 403 (origin), 429 (rate-limit), 500 (IO).
 */

import { randomUUID } from 'node:crypto';
import { consumeJti, extractJti, verifyChallenge } from './captcha.js';
import { defaultRateLimiter, type RateLimiter } from './rateLimit.js';
import { writeReport } from './storage.js';
import type { Report } from './types.js';
import { reportPayloadSchema } from './validation.js';

export interface HandleReportOptions {
  /** Données du form (déjà parsées en plain object). */
  formData: Record<string, string>;
  /** Origin header (CSRF check). `null` si absent. */
  origin: string | null;
  /** Host actuel (URL `${proto}://${host}`) pour comparer à `origin`. */
  selfOrigin: string;
  /** IP client (déjà extrait par le shim Astro depuis `clientAddress`). */
  ip: string;
  /** Injection (tests). */
  rateLimiter?: RateLimiter;
  /** Override (tests). */
  cwd?: string;
  /** Override `now` (tests). */
  now?: number;
}

export interface HandleReportResult {
  status: number;
  body: { success: boolean; id?: string; error?: string };
  /** Report construit (présent seulement sur 200) — pour la notif hors handler. */
  report?: Report;
}

const ALLOWED_ORIGIN_REGEX = /^https?:\/\/[^\s]+$/;

function originMatches(origin: string | null, selfOrigin: string): boolean {
  // En dev / preview, `selfOrigin` peut être `http://localhost:4321`.
  // En prod, le SITE_URL canonique. On accepte aussi un Origin absent quand
  // la requête provient d'un même-origin form classique (certains navigateurs
  // n'envoient pas Origin pour `<form>` POST same-origin) — dans ce cas, on
  // exige que le Referer existe (le shim passera Referer en fallback ⇒
  // l'appelant choisit lequel envoyer).
  if (!origin) return false;
  if (!ALLOWED_ORIGIN_REGEX.test(origin)) return false;
  try {
    return new URL(origin).origin === new URL(selfOrigin).origin;
  } catch {
    return false;
  }
}

export function handleReport(opts: HandleReportOptions): HandleReportResult {
  const limiter = opts.rateLimiter ?? defaultRateLimiter;
  const now = opts.now ?? Date.now();

  // 1. CSRF / Origin.
  if (!originMatches(opts.origin, opts.selfOrigin)) {
    return { status: 403, body: { success: false, error: 'origin invalide' } };
  }

  // 2. Honeypot (H16-1). Si rempli, on répond 204 (le bot enregistre un
  // succès et dégage — pas de feedback exploitable). Le champ est
  // `url_unused` (renommé depuis `website` qui auto-fillait sur Chrome).
  // On tolère encore l'ancien nom pour pas casser les anciens templates en
  // cache CDN pendant la migration — sera supprimé après une rotation.
  const honeypot = opts.formData.url_unused ?? opts.formData.website ?? '';
  if (honeypot.length > 0) {
    return { status: 204, body: { success: true } };
  }

  // 3. Validation Zod.
  const parsed = reportPayloadSchema.safeParse(opts.formData);
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    return {
      status: 400,
      body: { success: false, error: first ? `${first.path.join('.')}: ${first.message}` : 'payload invalide' },
    };
  }
  const data = parsed.data;

  // 4. Captcha — vérif signature + réponse. On NE CONSOMME PAS encore le jti :
  // le consommer avant la validation permettrait à un attaquant qui tape
  // `wrong` de griller des jetons légitimes.
  const captchaResult = verifyChallenge(data.captchaToken, data.captchaAnswer, now);
  if (captchaResult !== 'ok') {
    return { status: 400, body: { success: false, error: `captcha: ${captchaResult}` } };
  }

  // 5. Rate-limit AVANT de consommer le jti.
  //
  // L'ordre inverse brûlait le jeton d'un visiteur qui allait de toute façon
  // recevoir un 429 : Alice envoie un signalement, se trompe, renvoie 30 s
  // plus tard → le second POST passe le captcha, CONSOMME son jti, puis prend
  // un 429. Elle attend 5 minutes, reclique « Envoyer » sans recharger la
  // page — le jeton du champ caché est déjà consommé, elle reçoit
  // `400 captcha: replay`, un message qui l'accuse à tort de rejeu, et son
  // formulaire est bloqué jusqu'à rechargement complet.
  //
  // Accessoirement, cet ordre permettait de vider le cache anti-rejeu depuis
  // une IP pourtant limitée : 10 001 POST consommaient 10 001 jti et
  // évinçaient les plus anciens de la LRU (`JTI_CACHE_MAX`), rouvrant le rejeu
  // pour tout jeton encore dans sa fenêtre.
  if (!limiter.check(opts.ip, now)) {
    return { status: 429, body: { success: false, error: 'rate-limit (1 report / 5 min)' } };
  }

  // 6. Anti-rejeu (C16-3) — le jeton n'est consommé que lorsque le signalement
  // va réellement être écrit.
  const jti = extractJti(data.captchaToken);
  if (!consumeJti(jti)) {
    return { status: 400, body: { success: false, error: 'captcha: replay' } };
  }

  // 6. Construction + écriture.
  const report: Report = {
    id: `rep-${randomUUID()}`,
    sourceId: data.sourceId,
    recoId: data.recoId,
    category: data.category,
    details: data.details,
    submitter: {
      name: data.name && data.name.length > 0 ? data.name : undefined,
      email: data.email && data.email.length > 0 ? data.email : undefined,
      wantCredit: data.wantCredit === true,
    },
    submittedAt: new Date(now).toISOString(),
    status: 'pending',
    resolvedAt: null,
    resolvedBy: null,
    notes: null,
  };

  try {
    writeReport(report, opts.cwd);
  } catch (err) {
    // B-CRIT-1 : NE PAS renvoyer `err.message` au client. Une erreur d'écriture
    // porte l'arborescence ABSOLUE du serveur — un disque plein produisait
    // `IO: ENOSPC: no space left on device, open
    // '/srv/reco/tools/output/reports/<source>/rep-….json.tmp'`, livré tel quel
    // à un visiteur anonyme : chemin d'installation et emplacement exact du
    // stockage. On journalise côté serveur, on renvoie un code générique.
    //
    // Le module jumeau `src/lib/tracking/handler.ts` porte ce correctif et sa
    // justification depuis le départ ; il n'avait jamais été reporté ici.
    // eslint-disable-next-line no-console
    console.error('[reports/handler] writeReport failed', err);
    return { status: 500, body: { success: false, error: 'io' } };
  }

  return { status: 200, body: { success: true, id: report.id }, report };
}
