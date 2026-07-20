/**
 * src/lib/stats/slug.ts — Slug ASCII minimaliste et helpers de tri/hash.
 *
 * Pas de dépendance externe ; cohérent avec `tools/common.slugify` et
 * `tools/stats/aggregator._slugify`. Évite d'importer `gallery/slug.ts`
 * (autre périmètre / régressions).
 *
 * Issues fixées : R-P2-27 (factorisation), H26-2 (clé FR déterministe NFKD
 * comme Python — pas de `localeCompare` runtime-dependent), M26-19
 * (collisions slugify), H26-3 / H26-4 (hash stable pour ids DOM).
 */

/** Normalise un nom en slug ASCII (`Mary-Léa Dupont` → `mary-lea-dupont`). */
export function slugify(value: string): string {
  if (!value) return 'x';
  const norm = value
    .normalize('NFKD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return norm || 'x';
}

/**
 * Clé de tri stable insensible aux accents/casses — alignée sur
 * `tools/stats/aggregator._fr_sort_key`.
 *
 * Pourquoi pas `localeCompare(..., 'fr', { sensitivity: 'base' })` ?
 * → runtime-dependent (ICU embarqué Node vs navigateur diffère), ce qui
 * casse la garantie de build reproducible (H26-2).
 */
export function frSortKey(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();
}

/**
 * Hash stable type FNV-1a 32-bit, encodé base36 — utilisé pour générer des
 * IDs DOM déterministes au build (vs `Math.random` qui casserait la
 * reproductibilité — issues H26-3, H26-4).
 *
 * Collisions (F-L-1) : FNV-1a 32-bit a un espace de 2^32 valeurs. Sous le
 * seuil pratique de 100 entrées (chart titles, top lists), la probabilité
 * de collision est < 1 / 850 000 (paradoxe des anniversaires :
 * `n*(n-1)/(2*2^32)` ≈ 1.15e-6 pour n=100). On l'accepte : un id DOM
 * dupliqué pour deux titres simultanés est strictement impossible aux
 * volumes manipulés ici. Si l'usage scale, switcher vers SHA-1 base36.
 */
export function hashSlug(value: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h.toString(36);
}

/**
 * Déduplique les slugs en suffixant `-2`, `-3`… en cas de collision.
 *
 * Pourquoi : `slugify("Léa Martin")` et `slugify("Lea-Martin")` produisent
 * tous deux `lea-martin`. Sans dédoublonnement, le second écrase le
 * premier côté liens / ancres (M26-19).
 */
export function uniqueSlug(base: string, used: Set<string>): string {
  const root = slugify(base);
  if (!used.has(root)) {
    used.add(root);
    return root;
  }
  let n = 2;
  while (used.has(`${root}-${n}`)) n += 1;
  const out = `${root}-${n}`;
  used.add(out);
  return out;
}
