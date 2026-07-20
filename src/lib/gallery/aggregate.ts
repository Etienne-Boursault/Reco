/**
 * src/lib/gallery/aggregate.ts — Agrégation items × mentions pour les
 * galeries.
 *
 * Pures fonctions de transformation : on passe en entrée les listes
 * issues de `getCollection('items')` / `getCollection('mentions')`
 * (déjà filtrées par source), on sort en sortie des structures
 * directement consommables par les pages Astro `films.astro`, etc.
 *
 * Les citations ET les œuvres d'invité·es (`guestWork`, qui restent
 * `kind='reco'`) sont INCLUSES dans les compteurs de galerie : c'est une vue
 * d'ensemble (décision produit CR Story 4 — seule la page épisode sépare les
 * œuvres d'invités).
 *
 * Pas d'I/O ici — testable en isolation.
 */

export interface ItemLike {
  id: string;
  title: string;
  types: readonly string[];
  creator?: string | null;
  year?: number | null;
}

export interface MentionLike {
  itemId: string;
  recommendedBy?: string | null;
  kind?: 'reco' | 'citation';
  status?: 'draft' | 'validated' | 'discarded';
}

/** Vue agrégée d'un item pour les galeries (carte minimaliste). */
export interface GalleryEntry {
  id: string;
  title: string;
  types: readonly string[];
  creator: string | null;
  year: number | null;
  mentionCount: number;
}

const HIDDEN_STATUS = new Set(['discarded']);

/** Garde uniquement les mentions publiques (status != discarded). */
export function publicMentions(mentions: readonly MentionLike[]): MentionLike[] {
  return mentions.filter((m) => !HIDDEN_STATUS.has(m.status ?? 'draft'));
}

/**
 * Construit l'index `itemId → nb mentions publiques` (toutes catégories
 * de `kind` confondues — une citation compte aussi car la galerie est
 * une vue d'ensemble).
 */
export function countMentionsByItem(
  mentions: readonly MentionLike[],
): Map<string, number> {
  const counts = new Map<string, number>();
  for (const m of publicMentions(mentions)) {
    counts.set(m.itemId, (counts.get(m.itemId) ?? 0) + 1);
  }
  return counts;
}

/**
 * Sélectionne les items qui possèdent ≥1 occurrence parmi `types`
 * (inclusion : un item `['film', 'video']` matche `types=['film']`),
 * et qui ont au moins 1 mention publique. Tri par défaut :
 * `mentionCount DESC, title ASC` (locale FR).
 */
export function selectByType(
  items: readonly ItemLike[],
  mentions: readonly MentionLike[],
  types: readonly string[],
): GalleryEntry[] {
  const counts = countMentionsByItem(mentions);
  const wanted = new Set(types);
  const out: GalleryEntry[] = [];
  for (const it of items) {
    if (!it.types.some((t) => wanted.has(t))) continue;
    const n = counts.get(it.id) ?? 0;
    if (n === 0) continue;
    out.push({
      id: it.id,
      title: it.title,
      types: it.types,
      creator: it.creator ?? null,
      year: it.year ?? null,
      mentionCount: n,
    });
  }
  return sortGalleryEntries(out);
}

/**
 * Sélectionne les items recommandés par un invité (cas exact, casefold,
 * trim). Tri standard.
 */
export function selectByGuest(
  items: readonly ItemLike[],
  mentions: readonly MentionLike[],
  guestName: string,
): GalleryEntry[] {
  const needle = guestName.normalize('NFC').trim().toLowerCase();
  const itemIds = new Set<string>();
  const counts = new Map<string, number>();
  for (const m of publicMentions(mentions)) {
    const by = (m.recommendedBy ?? '').normalize('NFC').trim().toLowerCase();
    if (by !== needle) continue;
    itemIds.add(m.itemId);
    counts.set(m.itemId, (counts.get(m.itemId) ?? 0) + 1);
  }
  const out: GalleryEntry[] = [];
  for (const it of items) {
    if (!itemIds.has(it.id)) continue;
    out.push({
      id: it.id,
      title: it.title,
      types: it.types,
      creator: it.creator ?? null,
      year: it.year ?? null,
      mentionCount: counts.get(it.id) ?? 0,
    });
  }
  return sortGalleryEntries(out);
}

/**
 * Extrait tous les noms d'invités cités dans `mentions` (champ
 * `recommendedBy`), dédupliqués (casefold), triés A→Z (locale FR).
 *
 * Filtre les hôtes du podcast pour ne garder que les **invités**
 * (le sens galerie « invité » = personne ponctuelle, pas l'animateur·rice).
 */
export function listGuests(
  mentions: readonly MentionLike[],
  hosts: readonly string[] = [],
): string[] {
  const hostSet = new Set(hosts.map((h) => h.toLowerCase().trim()));
  const seen = new Map<string, string>();
  for (const m of publicMentions(mentions)) {
    const raw = (m.recommendedBy ?? '').trim();
    if (!raw) continue;
    const key = raw.toLowerCase();
    if (hostSet.has(key)) continue;
    if (!seen.has(key)) seen.set(key, raw);
  }
  return [...seen.values()].sort((a, b) =>
    a.localeCompare(b, 'fr', { sensitivity: 'base' }),
  );
}

/** Tri stable : `mentionCount DESC`, puis `title ASC` (locale FR). */
export function sortGalleryEntries(entries: GalleryEntry[]): GalleryEntry[] {
  return [...entries].sort((a, b) => {
    if (b.mentionCount !== a.mentionCount) return b.mentionCount - a.mentionCount;
    return a.title.localeCompare(b.title, 'fr', { sensitivity: 'base' });
  });
}
