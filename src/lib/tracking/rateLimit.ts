/**
 * src/lib/tracking/rateLimit.ts — Rate-limit IP in-memory pour /api/click.
 *
 * Objectif : borner les clics enregistrés à 60 par IP par fenêtre glissante
 * (default 60 s). Suffisant pour un usage humain normal (un visiteur clique
 * < 10 liens/min) ; bloque les bots qui spammeraient l'endpoint.
 *
 * Privacy (cohérent ADR 0034 reports/rateLimit) :
 *  - SHA-256(salt || ip) tronqué 12 bytes,
 *  - salt via `TRACKING_IP_SALT` (≥ 16 chars) sinon random au boot,
 *  - aucune IP en clair, aucune persistance.
 *
 * Localhost exempt (dev/test).
 */

import { createHmac, randomBytes } from 'node:crypto';

const DEFAULT_WINDOW_MS = 60 * 1000; // 1 min
const DEFAULT_MAX_HITS = 60;
const _LOCALHOST = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);

// M25-13 : déclaré AVANT getIpSalt() pour ne pas dépendre du TDZ.
const _bootSalt = randomBytes(16).toString('hex');

let _saltWarned = false;
function getIpSalt(): string {
  const fromEnv = process.env.TRACKING_IP_SALT;
  if (fromEnv && fromEnv.length >= 16) return fromEnv;
  if (!_saltWarned && process.env.RECO_QUIET !== '1') {
    _saltWarned = true;
    // eslint-disable-next-line no-console
    console.warn(
      '[tracking/rateLimit] TRACKING_IP_SALT manquant — salt random régénéré au boot. ' +
        'Configurer TRACKING_IP_SALT (≥ 16 chars) pour persister entre redéploiements.',
    );
  }
  return _bootSalt;
}

export function hashIp(ip: string): string {
  // B-MED-1 : HMAC-SHA256 plutôt que concat dans un SHA256 simple.
  // HMAC élimine les attaques d'extension de longueur et garantit que
  // la connaissance du préfixe (`salt`) ne permet pas de forger un hash
  // valide pour une autre IP. Cohérent ADR 0034.
  return createHmac('sha256', getIpSalt())
    .update(ip)
    .digest('hex')
    .slice(0, 24);
}

export interface RateLimiter {
  check(ip: string, now?: number): boolean;
  reset(): void;
  size(): number;
}

/**
 * Fenêtre glissante simple : on garde un tableau de timestamps par IP hash,
 * on purge ceux > windowMs, on autorise si < maxHits.
 *
 * H25-4 : GC amorti — au lieu de purger tout le store O(N) à CHAQUE check
 * passé 512 entrées (worst-case O(N × max_hits) par check), on déclenche
 * le sweep une fois tous les GC_INTERVAL checks. Charge amortie O(1) par
 * check, O(N) par sweep, déclenchement borné par compteur (pas timer pour
 * rester compatible serverless cold-start).
 */
// B-LOW-16 : valeurs configurables via env pour permettre un tuning ops
// (déploiement à forte charge → capacity plus grande, interval plus court).
// Fallback aux defaults safe si non définies / invalides.
function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}
const GC_CAPACITY = envInt('TRACKING_GC_CAPACITY', 512);
const GC_INTERVAL = envInt('TRACKING_GC_INTERVAL', 256);

export function createRateLimiter(
  windowMs: number = DEFAULT_WINDOW_MS,
  maxHits: number = DEFAULT_MAX_HITS,
): RateLimiter {
  const store = new Map<string, number[]>();
  let checksSinceGc = 0;

  function sweep(now: number): void {
    for (const [k, ts] of store) {
      const remain = ts.filter((t) => now - t < windowMs);
      if (remain.length === 0) store.delete(k);
      else store.set(k, remain);
    }
  }

  return {
    check(ip: string, now: number = Date.now()): boolean {
      if (_LOCALHOST.has(ip)) return true;
      const key = hashIp(ip);
      const hits = store.get(key) ?? [];
      const fresh = hits.filter((t) => now - t < windowMs);

      // GC amorti : déclenché tous les GC_INTERVAL checks SI le store
      // dépasse GC_CAPACITY. Évite O(N) à chaque check (H25-4).
      checksSinceGc += 1;
      if (store.size > GC_CAPACITY && checksSinceGc >= GC_INTERVAL) {
        sweep(now);
        checksSinceGc = 0;
      }

      if (fresh.length >= maxHits) {
        store.set(key, fresh);
        return false;
      }
      fresh.push(now);
      store.set(key, fresh);
      return true;
    },
    reset() {
      store.clear();
      checksSinceGc = 0;
    },
    size() {
      return store.size;
    },
  };
}

/**
 * B-NIT-11 : Singleton module-scope partagé entre toutes les requêtes
 * `/api/click` qui n'injectent pas leur propre limiter. State in-memory,
 * RAZ au cold-start (cohérent ADR 0034). Pour persister entre redéploiements
 * il faudrait un store externe (Redis / Durable Object) — hors scope Phase 4.
 */
export const defaultRateLimiter: RateLimiter = createRateLimiter();
