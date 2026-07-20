/**
 * src/lib/tracking/metrics.ts — Compteurs in-memory par status HTTP.
 *
 * R-P3-22 : `getClickMetrics()` expose un snapshot des compteurs (success,
 * 400, 403, 429, 500…). Dump prévu via futur endpoint admin Phase 4.5
 * (`/api/_admin/metrics`). Pas de persistance — RAZ au cold-start (cohérent
 * avec le rate-limit in-memory et ADR 0034).
 *
 * Privacy : zéro IP, zéro URL, zéro user-agent — juste des compteurs.
 */

const _counters = new Map<number, number>();

export function recordClickStatus(status: number): void {
  // B-MED-21 : on ignore tout code hors plage HTTP valide (100-599) pour
  // éviter qu'un appelant passe un entier arbitraire qui ferait gonfler
  // `byStatus` avec des clés type "-1" ou "99999".
  if (!Number.isInteger(status) || status < 100 || status > 599) return;
  _counters.set(status, (_counters.get(status) ?? 0) + 1);
}

export interface ClickMetrics {
  total: number;
  byStatus: Record<string, number>;
}

export function getClickMetrics(): ClickMetrics {
  let total = 0;
  const byStatus: Record<string, number> = {};
  for (const [code, n] of _counters) {
    byStatus[String(code)] = n;
    total += n;
  }
  return { total, byStatus };
}

export function resetClickMetrics(): void {
  _counters.clear();
}
