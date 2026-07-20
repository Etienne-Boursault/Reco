/**
 * src/lib/tracking/handler.ts — Logique métier de `/api/click`.
 *
 * Séparé de `src/pages/api/click.ts` pour être testable sans Astro.
 *
 * Couches d'acceptation (court-circuit dès le premier rejet) :
 *  1. `Sec-GPC` truthy (`'1'`, `'true'`, `1`, `true`) → 204 silencieux
 *     (respect du Global Privacy Control, cohérent ADR 0040, M25-8).
 *  2. Origin (POST strict, GET tolère Referer en fallback — H25-3 / H25-6).
 *  3. Honeypot rempli → 204 silencieux.
 *  4. Validation Zod du payload.
 *  5. Garde-fou date : si `getUTCFullYear()` NaN → 400 (H25-7).
 *  6. Rate-limit IP (60 clicks/min).
 *  7. Append via `ClickStorage` injecté (R-P1-14).
 *
 * Codes : 204 (ok — pas de body pour réduire poids), 400 (validation),
 *         403 (origin), 429 (rate-limit), 500 (IO).
 */

import { defaultRateLimiter, type RateLimiter } from './rateLimit.js';
import { JsonlClickStorage } from './storage.js';
import type { ClickEvent, ClickStorage } from './types.js';
import { clickPayloadSchema, sanitizeRef } from './validator.js';

export interface HandleClickOptions {
  /** Payload déjà parsé (JSON pour POST, query pour pixel GET). */
  payload: Record<string, unknown>;
  origin: string | null;
  /** Referer header — accepté uniquement si `allowReferer` (GET pixel). */
  referer?: string | null;
  selfOrigin: string;
  ip: string;
  /** Header `Sec-GPC` (`'1'`, `'true'` = opt-out — truthy check M25-8). */
  secGpc: string | null;
  /**
   * Si `true`, `referer` peut compléter `origin` pour la vérif same-origin
   * (cas du pixel GET où certains browsers ne joignent pas Origin). False
   * par défaut → POST strict (H25-3).
   */
  allowReferer?: boolean;
  rateLimiter?: RateLimiter;
  /** Backend de persistance injectable (R-P1-14). */
  storage?: ClickStorage;
  /** @deprecated utiliser `storage` (rétrocompat tests existants). */
  cwd?: string;
  now?: number;
}

export interface HandleClickResult {
  status: number;
  /** Pas de body pour 204 (réduction du poids). Body uniquement en erreur. */
  body?: { error: string };
}

// B-MED-18 : regex plus stricte — schema + host[:port] + path optionnel,
// pas de whitespace. Empêche les caractères de contrôle dans Origin.
const ALLOWED_ORIGIN_REGEX = /^https?:\/\/[a-zA-Z0-9.-]+(:[0-9]+)?(\/[^\s]*)?$/;

function originMatches(candidate: string | null, selfOrigin: string): boolean {
  if (!candidate) return false;
  if (!ALLOWED_ORIGIN_REGEX.test(candidate)) return false;
  try {
    return new URL(candidate).origin === new URL(selfOrigin).origin;
  } catch {
    return false;
  }
}

/**
 * M25-8 : Sec-GPC truthy check. Le standard W3C précise `'1'` mais des
 * UAs envoient `'true'` (Firefox dev), `1` numérique (proxies). Tout ce
 * qui est explicitement opt-out → on respecte.
 */
function isGpcOptOut(secGpc: string | null | undefined): boolean {
  if (secGpc === null || secGpc === undefined) return false;
  const normalized = String(secGpc).trim().toLowerCase();
  return normalized === '1' || normalized === 'true';
}

/**
 * B-NIT-11 : `defaultRateLimiter` est un singleton module-scope partagé entre
 * tous les appels qui n'injectent pas leur propre limiter. Cohérent avec
 * le besoin d'un état persistant entre requêtes pour borner les hits par IP.
 * Les tests injectent toujours leur propre limiter pour rester déterministes.
 */
export function handleClick(opts: HandleClickOptions): HandleClickResult {
  const limiter = opts.rateLimiter ?? defaultRateLimiter;
  const now = opts.now ?? Date.now();

  // 1. Global Privacy Control — silent opt-out, pas de log, pas de write.
  if (isGpcOptOut(opts.secGpc)) {
    return { status: 204 };
  }

  // 2. CSRF / Origin. POST → strict Origin. GET pixel → Referer toléré (H25-3 / H25-6).
  let originOk = originMatches(opts.origin, opts.selfOrigin);
  if (!originOk && opts.allowReferer) {
    originOk = originMatches(opts.referer ?? null, opts.selfOrigin);
  }
  if (!originOk) {
    return { status: 403, body: { error: 'origin invalide' } };
  }

  // 3. Honeypot — bot enregistre un succès silencieux et dégage.
  const trap = opts.payload.bot_trap;
  if (typeof trap === 'string' && trap.length > 0) {
    return { status: 204 };
  }

  // 4. Validation Zod.
  const parsed = clickPayloadSchema.safeParse(opts.payload);
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    return {
      status: 400,
      body: { error: first ? `${first.path.join('.')}: ${first.message}` : 'payload invalide' },
    };
  }
  const data = parsed.data;

  // 5. H25-7 / B-HIGH-8 — sanity check date :
  //   - `now` doit être un entier fini > 0 (rejette NaN / Infinity / négatif),
  //   - borne max ≈ 1er janvier 2100 UTC (4_102_444_800_000 ms epoch) pour
  //     éviter d'écrire un ts irréaliste (clock skew, attaquant injectant
  //     un payload arbitraire via un mock now).
  const NOW_MAX_MS = 4_102_444_800_000; // ≈ 2100-01-01T00:00:00Z
  if (!Number.isFinite(now) || now <= 0 || now >= NOW_MAX_MS) {
    return { status: 400, body: { error: 'ts invalide' } };
  }
  // `now` est ici un nombre fini positif et borné → `new Date(now)` produit
  // forcément un `Date` valide (pas besoin de re-tester `getUTCFullYear()`).
  const tsDate = new Date(now);

  // 6. Rate-limit.
  if (!limiter.check(opts.ip, now)) {
    return { status: 429, body: { error: 'rate-limit (60 clicks/min)' } };
  }

  // 7. Append via storage injecté (R-P1-14).
  // B-LOW-17 : `data.recoId ?? null` est redondant car Zod a déjà normalisé
  // `undefined → undefined` (le schéma a `.optional().nullable()`). On le
  // garde par défense en profondeur pour assurer la forme `string | null`
  // attendue par `ClickEvent` (jamais `undefined`).
  const event: ClickEvent = {
    ts: tsDate.toISOString(),
    url: data.url,
    category: data.category,
    sourceId: data.sourceId,
    recoId: data.recoId ?? null,
    ref: sanitizeRef(data.ref ?? null),
  };

  const storage = opts.storage ?? new JsonlClickStorage(opts.cwd);
  try {
    storage.append(event);
  } catch (err) {
    // B-CRIT-1 : NE PAS leak `err.message` côté client (peut contenir des
    // chemins FS, des secrets concatenés dans une erreur de driver, etc.).
    // On log côté serveur pour observabilité, on renvoie un code générique.
    // eslint-disable-next-line no-console
    console.error('[tracking/handler] storage append failed', err);
    return {
      status: 500,
      body: { error: 'io' },
    };
  }

  return { status: 204 };
}
