/**
 * Helpers de recherche tolérante (côté client).
 *
 *  - normalize()    : retire accents et casse pour comparer "vérino" et "verino".
 *  - levenshtein()  : distance d'édition (nb minimum d'opérations
 *                     insertion/suppression/substitution).
 *  - fuzzyMatch()   : combine substring et Levenshtein avec un seuil dépendant
 *                     de la longueur du token de la query.
 *
 * Ces fonctions sont volontairement pures et sans dépendance pour pouvoir
 * être incluses dans un `<script>` de page Astro (bundle client).
 */

/** Retire diacritiques + lowercase. `[̀-ͯ]` = combining marks. */
export function normalize(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

/** Distance de Levenshtein — implémentation O(m·n) à 2 lignes. */
export function levenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  let prev = new Array<number>(n + 1);
  let curr = new Array<number>(n + 1);
  for (let j = 0; j <= n; j++) prev[j] = j;
  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    [prev, curr] = [curr, prev];
  }
  return prev[n];
}

/**
 * Tous les tokens de `query` doivent matcher (substring OU Levenshtein) dans
 * `normalizedText`. Seuil dynamique :
 *  - 1 pour les tokens ≤ 4 caractères (évite les faux positifs),
 *  - 2 pour 5-7 caractères,
 *  - 3 au-delà.
 */
export function fuzzyMatch(query: string, normalizedText: string): boolean {
  const q = normalize(query).trim();
  if (!q) return true;
  const tokens = q.split(/\s+/);
  const words = normalizedText.split(/[\s'’,()/-]+/).filter(Boolean);
  for (const tok of tokens) {
    if (normalizedText.includes(tok)) continue;
    const threshold = tok.length <= 4 ? 1 : tok.length <= 7 ? 2 : 3;
    const ok = words.some((w) => {
      if (Math.abs(w.length - tok.length) > threshold) return false;
      return levenshtein(tok, w) <= threshold;
    });
    if (!ok) return false;
  }
  return true;
}
