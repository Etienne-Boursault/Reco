/**
 * src/lib/gallery/slug.ts — Slugification ASCII-safe pour URLs galerie.
 *
 * Règles :
 *  - minuscules
 *  - décomposition NFD + retrait des diacritiques (combining marks U+0300-036F)
 *  - remplacement des caractères non [a-z0-9] par `-`
 *  - compression des tirets consécutifs
 *  - retrait des tirets de tête/queue
 *
 * Exemples :
 *   slugify('Bong Joon-ho')       → 'bong-joon-ho'
 *   slugify('Étienne Daho')       → 'etienne-daho'
 *   slugify("  Jean-Marc d'Or  ") → 'jean-marc-d-or'
 *
 * Utilisé par `/[source]/invite/[name]` pour générer des URLs propres
 * et stables à partir des noms d'invités issus des collections Astro.
 */

/**
 * Convertit un nom (humain) en slug URL-safe.
 *
 * Retourne une chaîne vide si l'entrée est vide ou ne contient aucun
 * caractère alphanumérique (sécurité — empêche les routes `/invite//`).
 */
export function slugify(input: string | null | undefined): string {
  if (!input) return '';
  return input
    .normalize('NFD')
    // U+0300-036F = combining diacritical marks (accents)
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Construit un index `slug → nom d'affichage canonique` à partir d'une
 * liste de noms bruts. En cas de collision (deux noms qui slugifient
 * pareil), le premier nom rencontré gagne — déterministe pour `getStaticPaths`.
 */
export function buildGuestIndex(names: Iterable<string>): Map<string, string> {
  const index = new Map<string, string>();
  for (const name of names) {
    const slug = slugify(name);
    if (!slug) continue;
    if (!index.has(slug)) index.set(slug, name);
  }
  return index;
}
