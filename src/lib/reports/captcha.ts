/**
 * src/lib/reports/captcha.ts — Math captcha stateless signé HMAC-SHA256.
 *
 * Pourquoi pas reCAPTCHA ? Cf. ADR 0034 (RGPD, self-hosting).
 *
 * Principe (post-fixes C16-1/2/3) :
 *  - `generateChallenge()` tire deux entiers a,b ∈ [1..9] et renvoie un objet
 *    `{ question, token }`. Le payload contient un **hash** de la réponse
 *    (sha256(answer + jti + secret)) — JAMAIS la réponse en clair — un **jti**
 *    aléatoire (UUID v4 like) et un **exp** court (4h).
 *  - `verifyChallenge(token, answer)` recalcule le hash avec la réponse
 *    fournie et la signature HMAC du payload, compare en temps constant.
 *  - `consumeJti(jti)` marque un token comme utilisé (LRU bornée, anti-rejeu).
 *
 * Sécurité :
 *  - HMAC-SHA256 sur le payload entier (256 bits) ⇒ pas de forgery sans clé.
 *  - Comparaison `timingSafeEqual` ⇒ pas de side-channel.
 *  - Réponse hashée avec secret + jti ⇒ décoder le payload ne révèle PAS la
 *    réponse (fix C16-1).
 *  - TTL 4h + jti UUID + consommation unique ⇒ borne le rejeu (fix C16-3).
 *  - `REPORTS_SECRET` requis en production (fix C16-2).
 */

import { createHmac, randomBytes, timingSafeEqual } from 'node:crypto';

/**
 * TTL court : 4h. Un fork qui veut accepter les soumissions doit re-générer
 * les tokens côté SSR (cf. ADR 0034 / fork-guide). Le static build sert des
 * tokens valides pendant 4h après build — au-delà l'utilisateur recharge.
 */
const CHALLENGE_TTL_MS = 4 * 60 * 60 * 1000;
const DEV_SECRET_FALLBACK = 'reco-reports-dev-secret-do-not-use-in-prod';
const JTI_CACHE_MAX = 10000;
let _warnedMissingSecret = false;

export interface CaptchaChallenge {
  question: string;
  token: string;
}

interface CaptchaPayload {
  /** Hash sha256(answer + jti + secret) en base64url. La réponse n'est PAS en clair. */
  h: string;
  /** Timestamp d'expiry (ms epoch). */
  exp: number;
  /** Unique-use nonce, anti-rejeu. */
  jti: string;
}

function isProduction(): boolean {
  return process.env.NODE_ENV === 'production';
}

function isStrictMode(): boolean {
  // Opt-in : `REPORTS_REQUIRE_SECRET=1` lève si le secret est absent.
  // À activer en CI de déploiement réel (vs. CI de build du kit qui sert
  // juste à générer le HTML static demo).
  return process.env.REPORTS_REQUIRE_SECRET === '1';
}

function getSecret(): string {
  const fromEnv = process.env.REPORTS_SECRET;
  if (fromEnv && fromEnv.length >= 16) return fromEnv;
  // En mode strict (déploiement SSR réel), on lève — un secret manquant
  // signifierait des tokens signés avec une clé publique (fix C16-2).
  if (isStrictMode()) {
    throw new Error(
      '[reports/captcha] REPORTS_SECRET manquant ou trop court (<16 chars). ' +
        'Configurer REPORTS_SECRET en production (REPORTS_REQUIRE_SECRET=1).',
    );
  }
  // En prod sans opt-in strict (build du kit) : warning loud, fallback dev.
  if (isProduction() && !_warnedMissingSecret && process.env.RECO_QUIET !== '1') {
    _warnedMissingSecret = true;
    // eslint-disable-next-line no-console
    console.warn(
      '[reports/captcha] REPORTS_SECRET manquant en production — fallback dev utilisé. ' +
        'En déploiement réel : configurer REPORTS_SECRET ET REPORTS_REQUIRE_SECRET=1.',
    );
    return DEV_SECRET_FALLBACK;
  }
  if (!_warnedMissingSecret && process.env.RECO_QUIET !== '1') {
    _warnedMissingSecret = true;
    // eslint-disable-next-line no-console
    console.warn(
      '[reports/captcha] REPORTS_SECRET manquant — fallback dev. ' +
        'Configurer REPORTS_SECRET (≥ 16 chars) pour un déploiement SSR.',
    );
  }
  return DEV_SECRET_FALLBACK;
}

function sign(payloadB64: string): string {
  return createHmac('sha256', getSecret()).update(payloadB64).digest('base64url');
}

/**
 * Hash de la réponse, lié au jti et au secret. Permet de stocker dans le
 * payload une preuve que l'utilisateur connaît la réponse, SANS révéler
 * la réponse à qui décode le base64url (fix C16-1).
 */
function hashAnswer(answer: number | string, jti: string): string {
  return createHmac('sha256', getSecret())
    .update(`a:${answer}|j:${jti}`)
    .digest('base64url');
}

function b64encode(payload: CaptchaPayload): string {
  return Buffer.from(JSON.stringify(payload), 'utf8').toString('base64url');
}

function b64decode(b64: string): CaptchaPayload | null {
  try {
    const json = Buffer.from(b64, 'base64url').toString('utf8');
    const obj = JSON.parse(json) as unknown;
    if (
      obj &&
      typeof obj === 'object' &&
      typeof (obj as CaptchaPayload).h === 'string' &&
      typeof (obj as CaptchaPayload).exp === 'number' &&
      typeof (obj as CaptchaPayload).jti === 'string'
    ) {
      return obj as CaptchaPayload;
    }
    return null;
  } catch {
    return null;
  }
}

/** UUID-v4-like (16 bytes random → base64url, ~22 chars). */
function newJti(): string {
  return randomBytes(16).toString('base64url');
}

/**
 * Tire une paire (a, b) ∈ [1..9]² et renvoie la question + token signé.
 *
 * `rng` est injectable pour les tests (par défaut `Math.random`).
 */
export function generateChallenge(
  now: number = Date.now(),
  rng: () => number = Math.random,
  jtiFn: () => string = newJti,
): CaptchaChallenge {
  const a = 1 + Math.floor(rng() * 9);
  const b = 1 + Math.floor(rng() * 9);
  const sum = a + b;
  const jti = jtiFn();
  const payloadB64 = b64encode({
    h: hashAnswer(sum, jti),
    exp: now + CHALLENGE_TTL_MS,
    jti,
  });
  const sig = sign(payloadB64);
  return {
    question: `Combien font ${a} + ${b} ?`,
    token: `${payloadB64}.${sig}`,
  };
}

/**
 * Vérifie un token + une réponse utilisateur. Renvoie un code stable.
 *
 * Codes :
 *  - `ok`       : signature OK, non expiré, réponse correcte.
 *  - `invalid`  : format/signature/payload invalide (fraude probable).
 *  - `expired`  : signature OK mais token périmé.
 *  - `wrong`    : signature OK, non expiré, mauvaise réponse.
 *
 * NB : la consommation anti-rejeu (jti unique) est gérée séparément par
 * `consumeJti()` côté handler.
 */
export type VerifyResult = 'ok' | 'invalid' | 'expired' | 'wrong';

export function verifyChallenge(
  token: string | null | undefined,
  userAnswer: string | number | null | undefined,
  now: number = Date.now(),
): VerifyResult {
  if (!token || typeof token !== 'string') return 'invalid';
  const parts = token.split('.');
  if (parts.length !== 2) return 'invalid';
  const [payloadB64, providedSig] = parts;

  // Signature constant-time. timingSafeEqual exige même longueur ⇒ guard.
  const expectedSig = sign(payloadB64);
  const a = Buffer.from(expectedSig, 'utf8');
  const b = Buffer.from(providedSig, 'utf8');
  if (a.length !== b.length || !timingSafeEqual(a, b)) return 'invalid';

  const payload = b64decode(payloadB64);
  if (!payload) return 'invalid';
  if (payload.exp < now) return 'expired';

  // Réponse utilisateur : tolère espaces autour, mais doit être un entier.
  const raw =
    typeof userAnswer === 'number' ? String(userAnswer) : (userAnswer ?? '').toString().trim();
  if (!/^-?\d+$/.test(raw)) return 'wrong';

  // Comparer le hash attendu (recalculé) vs celui du payload, en temps constant.
  const expectedHash = hashAnswer(Number(raw), payload.jti);
  const ah = Buffer.from(expectedHash, 'utf8');
  const bh = Buffer.from(payload.h, 'utf8');
  if (ah.length !== bh.length || !timingSafeEqual(ah, bh)) return 'wrong';
  return 'ok';
}

/**
 * Extrait le `jti` d'un token (sans valider la signature). Utilisé par les
 * tests ou par le handler pour journaliser. NE PAS l'utiliser pour décider
 * de la validité — passer par `verifyChallenge` d'abord.
 */
export function extractJti(token: string): string | null {
  if (!token || typeof token !== 'string') return null;
  const parts = token.split('.');
  if (parts.length !== 2) return null;
  const p = b64decode(parts[0]);
  return p?.jti ?? null;
}

/**
 * Cache LRU borné des jti consommés (fix C16-3, anti-rejeu).
 * Implémentation Set + tracking d'insertion order (Map<string, true>).
 * Note : in-memory ⇒ scope process. En multi-instance, partager via Redis.
 */
const _consumedJti: Map<string, true> = new Map();

/**
 * Marque un jti comme consommé. Renvoie `true` si c'est la PREMIÈRE fois
 * (token utilisable), `false` si déjà vu (rejeu détecté).
 */
export function consumeJti(jti: string | null | undefined): boolean {
  if (!jti || typeof jti !== 'string') return false;
  if (_consumedJti.has(jti)) return false;
  _consumedJti.set(jti, true);
  // Eviction LRU simple : si on dépasse la borne, supprimer la plus ancienne
  // (Map garde l'ordre d'insertion).
  if (_consumedJti.size > JTI_CACHE_MAX) {
    const oldest = _consumedJti.keys().next().value;
    if (oldest !== undefined) _consumedJti.delete(oldest);
  }
  return true;
}

/** Pour les tests : reset du cache de jti consommés. */
export function _resetConsumedJti(): void {
  _consumedJti.clear();
}
