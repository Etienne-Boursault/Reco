/**
 * src/lib/search/normalize.ts — Normalisation FR-friendly pour la recherche.
 *
 * - lowercase
 * - décomposition NFD + retrait des diacritiques (accents)
 * - retrait des caractères non alphanumériques (utile pour comparer
 *   "Bong Joon-ho" vs "bong joonho")
 *
 * Utilisé à la fois pour les champs indexés (MiniSearch processTerm) et
 * pour les requêtes utilisateur (MiniSearch tokenize/processTerm). Garantit
 * que "Parasite" matche "Parásite" et "kaamelott" matche "Kaâmelott".
 *
 * Pure — aucune dépendance, testable en isolation.
 */

/** Tokenizer + processeur compatible MiniSearch (signature: term -> term|null). */
export function stripDiacritics(input: string): string {
  return input.normalize('NFD').replace(/\p{M}/gu, '');
}

/** Normalise un terme pour l'indexation/la recherche (FR). */
export function normalizeTerm(input: string): string {
  return stripDiacritics(input).toLowerCase();
}

/**
 * Tokenizer FR : sépare sur tout ce qui n'est pas lettre/chiffre (après
 * retrait des accents). Filtre les tokens vides.
 */
export function tokenizeFR(input: string): string[] {
  if (!input) return [];
  return stripDiacritics(input)
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length > 0);
}
