/**
 * src/lib/stats/formatter.ts — Helpers de formatage des compteurs stats.
 *
 * Cf. ADR 0047. Pures fonctions sans dépendance Astro.
 */

/**
 * Formate un compteur entier de façon compacte :
 *   - < 1 000             → tel quel (ex. `42`)
 *   - 1 000 ≤ n < 1 000 000 → `1.2k` (1 décimale, tronquée si entière)
 *   - ≥ 1 000 000          → `1.2M`
 *
 * Toujours en notation anglo-saxonne (`.` décimal, pas d'espace) car
 * destiné aux gros chiffres en exergue (lisibilité tableau de bord). La
 * version localisée FR est gérée par `formatCount`.
 */
export function formatCompact(n: number): string {
  if (!Number.isFinite(n) || n < 0) return '0';
  if (n < 1000) return String(Math.trunc(n));
  if (n < 1_000_000) return `${trim(n / 1000)}k`;
  return `${trim(n / 1_000_000)}M`;
}

/**
 * Formate un compteur en respectant la locale FR :
 *   - séparateurs de milliers `1 234`
 *   - pas de décimales
 *
 * Pour les chiffres principaux du tableau de bord. `formatCompact` est
 * réservé aux contextes contraints (mobile, badges).
 *
 * @param n Compteur entier (les fractions sont tronquées).
 * @param locale BCP 47 — `'fr-FR'` par défaut. Override utile pour les
 *   forks i18n (`'en-US'`, `'de-DE'`…) ou les tests qui veulent forcer une
 *   locale précise indépendamment de l'environnement Node.
 */
export function formatCount(n: number, locale = 'fr-FR'): string {
  if (!Number.isFinite(n) || n < 0) return '0';
  return Math.trunc(n).toLocaleString(locale);
}

/**
 * Formate une fraction `[0, 1]` en pourcentage entier (`0.421` → `"42%"`).
 * Utilisé pour les libellés ARIA des bar charts.
 */
export function formatPercent(fraction: number): string {
  if (!Number.isFinite(fraction) || fraction < 0) return '0%';
  return `${Math.round(fraction * 100)}%`;
}

/**
 * Tronque à 1 décimale en supprimant `.0` final pour la compacité.
 *
 * Pipeline (L26-25) :
 *  1. `Math.floor(x * 10) / 10` → troncature stricte (pas d'arrondi
 *     bancaire) : `1.999 → 1.9` et non `2.0`. Évite la sur-estimation
 *     dans les badges « 1.0k » qui en pratique sont à 999.
 *  2. `.toFixed(1)` → forme canonique `"1.9"` ou `"1.0"` (gestion
 *     uniforme des entiers comme `"1.0"`).
 *  3. Strip `.0` final → `"1.0"` devient `"1"` (compacité visuelle).
 */
function trim(x: number): string {
  const rounded = Math.floor(x * 10) / 10;
  const s = rounded.toFixed(1);
  return s.endsWith('.0') ? s.slice(0, -2) : s;
}
