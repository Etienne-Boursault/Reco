/**
 * src/lib/reports/rateLimit.ts — Rate-limit IP in-memory.
 *
 * Objectif : 1 report par IP par fenêtre (default 5 min). Suffisant pour le
 * volume cible (kit petite échelle). Reset au redéploiement, ce qu'on
 * accepte (cf. ADR 0034).
 *
 * Privacy : l'IP n'est jamais stockée en clair. On hash en SHA-256 tronqué
 * sur 12 bytes (24 hex) — collision improbable à l'échelle visée, et
 * irréversible sans dictionnaire (un attaquant qui aurait la base devrait
 * brute-forcer 2^96 IPs).
 *
 * Localhost (`127.0.0.1`, `::1`) est exempté pour permettre le dev/test.
 */

import { createHash, randomBytes } from 'node:crypto';

const DEFAULT_WINDOW_MS = 5 * 60 * 1000; // 5 min
const _LOCALHOST = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);

/**
 * Salt pour le hash des IP (H16-3). Sans salt, un attaquant qui obtient le
 * store peut brute-forcer le hash en énumérant l'espace IPv4 (~2^32). Avec
 * salt :
 *  - en prod, fournir `REPORTS_IP_SALT` (≥ 16 chars) — persistant entre
 *    redéploiements pour garder le rate-limit cohérent.
 *  - sans env var, on génère un salt aléatoire au boot (perdu au restart,
 *    acceptable car le rate-limit est de toute façon reset).
 */
let _saltWarned = false;
function getIpSalt(): string {
  const fromEnv = process.env.REPORTS_IP_SALT;
  if (fromEnv && fromEnv.length >= 16) return fromEnv;
  if (!_saltWarned && process.env.RECO_QUIET !== '1') {
    _saltWarned = true;
    // eslint-disable-next-line no-console
    console.warn(
      '[reports/rateLimit] REPORTS_IP_SALT manquant — salt random régénéré au boot. ' +
        'Configurer REPORTS_IP_SALT (≥ 16 chars) pour persister entre redéploiements.',
    );
  }
  return _bootSalt;
}
const _bootSalt = randomBytes(16).toString('hex');

export interface RateLimiter {
  /** Renvoie `true` si la requête est autorisée, `false` si rate-limitée. */
  check(ip: string, now?: number): boolean;
  /** Vide le store (tests). */
  reset(): void;
  /** Nombre d'IPs actuellement trackées (observabilité). */
  size(): number;
}

function hashIp(ip: string): string {
  return createHash('sha256')
    .update(getIpSalt())
    .update('|')
    .update(ip)
    .digest('hex')
    .slice(0, 24);
}

/**
 * Crée un rate-limiter avec une fenêtre glissante simple (dernière requête).
 *
 * Algorithme : on stocke `lastAt` par IP hash. Une requête est acceptée si
 * `now - lastAt >= windowMs`. À chaque acceptation, on met à jour `lastAt`.
 *
 * On GC opportuniste les entrées > 10× windowMs à chaque check pour borner
 * la mémoire (pas de timer ⇒ pas de leak côté event-loop).
 */
export function createRateLimiter(windowMs: number = DEFAULT_WINDOW_MS): RateLimiter {
  const store = new Map<string, number>();
  const gcThreshold = windowMs * 10;

  return {
    check(ip: string, now: number = Date.now()): boolean {
      if (_LOCALHOST.has(ip)) return true;
      const key = hashIp(ip);
      const last = store.get(key);

      // GC opportuniste : si le store grossit, on purge les entrées vieilles.
      if (store.size > 256) {
        for (const [k, t] of store) {
          if (now - t > gcThreshold) store.delete(k);
        }
      }

      if (last !== undefined && now - last < windowMs) return false;
      store.set(key, now);
      return true;
    },
    reset() {
      store.clear();
    },
    size() {
      return store.size;
    },
  };
}

/**
 * Singleton process-wide pour l'endpoint /api/report.
 *
 * Exporté pour les tests qui veulent injecter un autre limiter ; en prod
 * tous les appels au handler partagent cette instance.
 */
export const defaultRateLimiter: RateLimiter = createRateLimiter();
