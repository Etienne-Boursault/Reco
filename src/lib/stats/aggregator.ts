/**
 * src/lib/stats/aggregator.ts — Agrégation pure items × mentions × episodes
 * pour les pages stats publiques.
 *
 * Cf. ADR 0047. Pures fonctions, idempotentes (tri stable, pas d'aléa).
 *
 * Filtrage : on exclut systématiquement les mentions `status='discarded'`
 * (cohérent avec `gallery/aggregate.ts::publicMentions`). Les citations
 * (`kind='citation'`) sont incluses car la stat est une vue d'ensemble.
 * Les œuvres d'invité·es (`guestWork`) restent `kind='reco'` et sont donc
 * comptées comme des recommandations normales ici (décision produit CR
 * Story 4 : seule la page épisode les présente à part).
 *
 * Issues fixées :
 *  - H26-2 : tri via `frSortKey` (NFKD) déterministe au lieu de
 *    `localeCompare` (ICU runtime-dependent).
 *  - M26-6 : `coerceMonth` borne l'année à [1900, 2100] (filtre les dates
 *    aberrantes type 0001 ou 9999).
 *  - M26-19 : dédoublonnement des slugs (collisions accents).
 *  - L26-27 : `computeTypeDistribution` tri secondaire `count DESC` puis
 *    alpha.
 *  - R-P3-30 : `monthlyEpisodes` remplit les mois manquants avec `count=0`
 *    entre min et max pour des charts continus.
 */
import { frSortKey, slugify, uniqueSlug } from './slug';
import type {
  GlobalCounts,
  MonthlyBucket,
  StatsSnapshot,
  TopGuest,
  TopWork,
} from './types';
import { STATS_SCHEMA_VERSION } from './types';

const HIDDEN_STATUS = new Set(['discarded']);

/**
 * Borne inférieure de l'année acceptée par `coerceMonth`.
 *
 * Pourquoi : filtre les dates aberrantes type `0001-01-01` qu'on rencontre
 * parfois dans les flux RSS mal formés (M26-6). Exporté pour réutilisation
 * dans les tests et les scripts Python miroirs (`tools/stats/aggregator.py`).
 */
export const MONTH_MIN_YEAR = 1900;

/**
 * Borne supérieure de l'année acceptée par `coerceMonth`.
 *
 * Pourquoi : filtre les dates aberrantes type `9999-12-31` (sentinelles RSS,
 * timestamps mal convertis). Exporté pour réutilisation dans les tests et
 * les scripts Python miroirs.
 */
export const MONTH_MAX_YEAR = 2100;

/**
 * Fenêtre maximale (en mois) du chart « épisodes/mois » (F-CRIT-9).
 *
 * Pourquoi : `computeMonthlyEpisodes` remplit les mois manquants entre min
 * et max pour des charts continus (R-P3-30). Sans cap, une mention parasite
 * avec une date du futur (ou des archives 1990) produirait des milliers de
 * buckets vides et exploserait le HTML/SVG. On garde 5 ans glissants à
 * partir du dernier mois observé.
 */
export const MONTHLY_WINDOW_MAX = 60;

// --- Inputs (formes minimales — duck-typing pour testabilité) ---------------

export interface ItemLike {
  id: string;
  title: string;
  types: readonly string[];
}

export interface MentionLike {
  itemId: string;
  recommendedBy?: string | null;
  status?: 'draft' | 'validated' | 'discarded';
  sourceRef: { sourceId: string };
}

export interface EpisodeLike {
  sourceId: string;
  date?: Date | string | null;
}

export interface SourceLike {
  id: string;
  hosts?: readonly string[];
}

export interface AggregateOptions {
  topGuestsLimit?: number;
  topWorksLimit?: number;
  /** Restreint l'agrégation à une source unique (pour `/[source]/stats`). */
  sourceId?: string;
  /** ISO timestamp à inscrire dans `generatedAt`. Défaut : `new Date().toISOString()`. */
  generatedAt?: string;
}

// --- Helpers ----------------------------------------------------------------

/** Garde uniquement les mentions publiques. */
export function publicMentions(mentions: readonly MentionLike[]): MentionLike[] {
  return mentions.filter((m) => !HIDDEN_STATUS.has(m.status ?? 'draft'));
}

function buildHostSet(sources: readonly SourceLike[]): Set<string> {
  const hosts = new Set<string>();
  for (const s of sources) {
    for (const h of s.hosts ?? []) {
      const k = h.trim().toLowerCase();
      if (k) hosts.add(k);
    }
  }
  return hosts;
}

/** Décale un mois ISO `YYYY-MM` de `delta` mois (peut être négatif). */
function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split('-').map((n) => Number(n));
  // Index 0-based pour rester dans l'arithmétique modulo 12 propre.
  const total = y * 12 + (m - 1) + delta;
  const ny = Math.floor(total / 12);
  const nm = (total % 12 + 12) % 12 + 1;
  return `${ny}-${String(nm).padStart(2, '0')}`;
}

function coerceMonth(date: Date | string | null | undefined): string | null {
  if (!date) return null;
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return null;
  const y = d.getUTCFullYear();
  if (y < MONTH_MIN_YEAR || y > MONTH_MAX_YEAR) return null;
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  return `${y}-${m}`;
}

// --- Counts ------------------------------------------------------------------

/**
 * Calcule les compteurs globaux à partir des collections déjà filtrées.
 * Le filtrage par source doit avoir été appliqué en amont si nécessaire.
 */
export function computeGlobalCounts(args: {
  sources: readonly SourceLike[];
  episodes: readonly EpisodeLike[];
  mentions: readonly MentionLike[];
  items: readonly ItemLike[];
}): GlobalCounts {
  const pub = publicMentions(args.mentions);
  const hosts = buildHostSet(args.sources);
  const mentionedItemIds = new Set<string>();
  const guests = new Set<string>();
  for (const m of pub) {
    mentionedItemIds.add(m.itemId);
    const by = (m.recommendedBy ?? '').trim();
    if (!by) continue;
    const key = by.toLowerCase();
    if (hosts.has(key)) continue;
    guests.add(key);
  }
  // Une œuvre n'est comptée que si elle est effectivement mentionnée et présente
  // dans le catalogue d'items (cohérent avec les galeries).
  const itemIds = new Set(args.items.map((i) => i.id));
  let uniqueWorks = 0;
  for (const id of mentionedItemIds) if (itemIds.has(id)) uniqueWorks += 1;

  return {
    podcastsCount: args.sources.length,
    episodesCount: args.episodes.length,
    recommendationsCount: pub.length,
    uniqueWorksCount: uniqueWorks,
    uniqueGuestsCount: guests.size,
  };
}

// --- Top guests --------------------------------------------------------------

export function computeTopGuests(
  mentions: readonly MentionLike[],
  sources: readonly SourceLike[],
  limit = 10,
): TopGuest[] {
  const hosts = buildHostSet(sources);
  /**
   * F-H-14 : par clé lower-case, on garde un Counter des variantes du nom
   * croisées dans les mentions. À la sortie on choisit la forme la plus
   * fréquente (tie → on préfère la version avec au moins une majuscule —
   * « Alice » vs « alice » — qui reflète une saisie soignée).
   */
  const counts = new Map<
    string,
    { variants: Map<string, number>; count: number }
  >();
  for (const m of publicMentions(mentions)) {
    const raw = (m.recommendedBy ?? '').trim();
    if (!raw) continue;
    const key = raw.toLowerCase();
    if (hosts.has(key)) continue;
    let cur = counts.get(key);
    if (!cur) {
      cur = { variants: new Map(), count: 0 };
      counts.set(key, cur);
    }
    cur.count += 1;
    cur.variants.set(raw, (cur.variants.get(raw) ?? 0) + 1);
  }
  function pickName(variants: Map<string, number>): string {
    let bestName = '';
    let bestCount = -1;
    let bestHasUpper = false;
    for (const [name, n] of variants) {
      const hasUpper = name !== name.toLowerCase();
      if (n > bestCount) {
        bestName = name;
        bestCount = n;
        bestHasUpper = hasUpper;
      } else if (n === bestCount && hasUpper && !bestHasUpper) {
        // Tie → préfère la version capitalisée.
        bestName = name;
        bestHasUpper = true;
      }
    }
    return bestName;
  }
  const resolved = [...counts.values()].map(({ variants, count }) => ({
    name: pickName(variants),
    count,
  }));
  const entries = resolved.sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    const ka = frSortKey(a.name);
    const kb = frSortKey(b.name);
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  });
  const used = new Set<string>();
  return entries.slice(0, limit).map(({ name, count }) => ({
    name,
    slug: uniqueSlug(name, used),
    count,
  }));
}

// --- Top works ---------------------------------------------------------------

export function computeTopWorks(
  items: readonly ItemLike[],
  mentions: readonly MentionLike[],
  limit = 10,
): TopWork[] {
  const counts = new Map<string, number>();
  for (const m of publicMentions(mentions)) {
    counts.set(m.itemId, (counts.get(m.itemId) ?? 0) + 1);
  }
  const itemById = new Map(items.map((i) => [i.id, i]));
  const out: TopWork[] = [];
  for (const [id, n] of counts) {
    const it = itemById.get(id);
    if (!it) continue;
    out.push({
      id,
      title: it.title,
      type: it.types[0] ?? 'autre',
      mentionsCount: n,
    });
  }
  out.sort((a, b) => {
    if (b.mentionsCount !== a.mentionsCount) return b.mentionsCount - a.mentionsCount;
    const ka = frSortKey(a.title);
    const kb = frSortKey(b.title);
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  });
  return out.slice(0, limit);
}

// --- Type distribution -------------------------------------------------------

/**
 * Distribution `type → count` (1 item par type primaire = `types[0]`).
 * Une œuvre n'apparaît qu'une fois (clé `id`), agrégée sur son type principal.
 *
 * Tri : `count DESC` puis alpha (L26-27).
 */
export function computeTypeDistribution(
  items: readonly ItemLike[],
  mentions: readonly MentionLike[],
): Record<string, number> {
  const mentionedIds = new Set<string>();
  for (const m of publicMentions(mentions)) mentionedIds.add(m.itemId);
  const dist: Record<string, number> = {};
  for (const it of items) {
    if (!mentionedIds.has(it.id)) continue;
    const t = it.types[0] ?? 'autre';
    dist[t] = (dist[t] ?? 0) + 1;
  }
  const sortedKeys = Object.keys(dist).sort((a, b) => {
    if (dist[b] !== dist[a]) return dist[b] - dist[a];
    const ka = frSortKey(a);
    const kb = frSortKey(b);
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  });
  const sorted: Record<string, number> = {};
  for (const k of sortedKeys) sorted[k] = dist[k];
  return sorted;
}

// --- Monthly episodes --------------------------------------------------------

/**
 * Agrège les épisodes par mois ISO `YYYY-MM` et **remplit les mois
 * manquants entre min et max avec `count=0`** (R-P3-30) pour des charts
 * continus (sinon les bar charts laissent des trous trompeurs).
 *
 * F-CRIT-9 : la fenêtre est **cappée à `MONTHLY_WINDOW_MAX` mois** (60 par
 * défaut) à partir du dernier mois observé. Sans cap, une seule date
 * aberrante (futur 2099, archive 1995…) produirait des centaines de buckets
 * vides et exploserait le SVG / le HTML.
 */
export function computeMonthlyEpisodes(
  episodes: readonly EpisodeLike[],
): MonthlyBucket[] {
  const counts = new Map<string, number>();
  for (const e of episodes) {
    const m = coerceMonth(e.date);
    if (!m) continue;
    counts.set(m, (counts.get(m) ?? 0) + 1);
  }
  if (counts.size === 0) return [];
  const present = [...counts.keys()].sort();
  let first = present[0];
  const last = present[present.length - 1];
  // F-CRIT-9 — Cap la fenêtre à `MONTHLY_WINDOW_MAX` mois.
  const minAllowed = shiftMonth(last, -(MONTHLY_WINDOW_MAX - 1));
  if (first < minAllowed) first = minAllowed;
  const out: MonthlyBucket[] = [];
  let [y, mo] = first.split('-').map((n) => Number(n));
  const [yLast, moLast] = last.split('-').map((n) => Number(n));
  while (y < yLast || (y === yLast && mo <= moLast)) {
    const key = `${y}-${String(mo).padStart(2, '0')}`;
    out.push({ month: key, count: counts.get(key) ?? 0 });
    mo += 1;
    if (mo > 12) {
      mo = 1;
      y += 1;
    }
  }
  return out;
}

// --- Per-source --------------------------------------------------------------

export function computePerSource(args: {
  sources: readonly SourceLike[];
  episodes: readonly EpisodeLike[];
  mentions: readonly MentionLike[];
  items: readonly ItemLike[];
}): Record<string, GlobalCounts> {
  const out: Record<string, GlobalCounts> = {};
  for (const s of args.sources) {
    const eps = args.episodes.filter((e) => e.sourceId === s.id);
    const mens = args.mentions.filter((m) => m.sourceRef.sourceId === s.id);
    const mentionedIds = new Set(mens.map((m) => m.itemId));
    const its = args.items.filter((i) => mentionedIds.has(i.id));
    out[s.id] = computeGlobalCounts({
      sources: [s],
      episodes: eps,
      mentions: mens,
      items: its,
    });
  }
  return out;
}

// --- Build reproductibilité --------------------------------------------------

/**
 * Résout `generatedAt` depuis les variables d'environnement de build :
 *  1. `SOURCE_DATE_EPOCH` — secondes Unix (convention reproducible-builds.org).
 *  2. `RECO_BUILD_TIMESTAMP` — ISO 8601 brut (override projet).
 *
 * Retourne `null` si aucune var n'est positionnée / parseable, charge à
 * l'appelant de fallback sur `new Date().toISOString()`.
 */
function resolveGeneratedAtFromEnv(): string | null {
  const epoch = process.env.SOURCE_DATE_EPOCH;
  if (epoch && /^\d+$/.test(epoch)) {
    const sec = Number(epoch);
    if (Number.isFinite(sec)) {
      const iso = new Date(sec * 1000).toISOString();
      // Normalise sur la forme stricte attendue par `statsSnapshotSchema`
      // (avec millisecondes — `toISOString` la produit déjà).
      return iso;
    }
  }
  const raw = process.env.RECO_BUILD_TIMESTAMP;
  if (raw && raw.trim()) return raw.trim();
  return null;
}

// --- Façade ------------------------------------------------------------------

export function buildStatsSnapshot(args: {
  sources: readonly SourceLike[];
  episodes: readonly EpisodeLike[];
  mentions: readonly MentionLike[];
  items: readonly ItemLike[];
  options?: AggregateOptions;
}): StatsSnapshot {
  const opts = args.options ?? {};
  let sources = args.sources;
  let episodes = args.episodes;
  let mentions = args.mentions;
  let items = args.items;
  if (opts.sourceId) {
    sources = sources.filter((s) => s.id === opts.sourceId);
    episodes = episodes.filter((e) => e.sourceId === opts.sourceId);
    mentions = mentions.filter((m) => m.sourceRef.sourceId === opts.sourceId);
    const mentionedIds = new Set(mentions.map((m) => m.itemId));
    items = items.filter((i) => mentionedIds.has(i.id));
  }

  // F-CRIT-4 — build reproductible : priorité aux env vars `SOURCE_DATE_EPOCH`
  // (convention reproducible-builds.org) puis `RECO_BUILD_TIMESTAMP`, puis
  // fallback temps réel. Permet à un re-build de produire un snapshot
  // bit-identique aux fins de cache CDN / signatures.
  const generatedAt =
    opts.generatedAt ??
    resolveGeneratedAtFromEnv() ??
    new Date().toISOString();

  return {
    schemaVersion: STATS_SCHEMA_VERSION,
    generatedAt,
    global: computeGlobalCounts({ sources, episodes, mentions, items }),
    perSource: computePerSource({ sources, episodes, mentions, items }),
    topGuests: computeTopGuests(mentions, sources, opts.topGuestsLimit ?? 50),
    topWorks: computeTopWorks(items, mentions, opts.topWorksLimit ?? 50),
    typeDistribution: computeTypeDistribution(items, mentions),
    monthlyEpisodes: computeMonthlyEpisodes(episodes),
  };
}

// Re-export pour rétrocompat des tests existants qui importent slugify
// depuis `./slug` (ne pas casser l'API publique du package).
export { slugify };
