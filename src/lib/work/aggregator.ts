/**
 * src/lib/work/aggregator.ts — Aggrégation cross-épisodes par œuvre.
 *
 * Sert la page canonique d'œuvre (`/<source>/oeuvre/<itemId>`). Le pipeline
 * stocke les Items (œuvres dédupliquées) et Mentions (occurrences) dans des
 * collections distinctes (cf. ADR 0001-0004). Cette page regroupe toutes les
 * mentions pointant vers un même item, jointe aux épisodes correspondants.
 *
 * Module **pur** (aucune dépendance Astro/fs) pour rester testable et
 * partageable côté build et côté composants. Cf. ADR 0032.
 */
import { creatorBasedProvider } from './similarity';

/** Snapshot minimal d'un Item utile pour la page (cf. collection `items`). */
export interface ItemLike {
  id: string;
  title: string;
  types: string[];
  creator?: string | null;
  year?: number | null;
  externalIds?: Record<string, unknown>;
  customLinks?: { label: string; url: string }[];
  watchProviders?: { name: string; url: string; ethics?: string | null }[];
}

/** Snapshot minimal d'une Mention. */
export interface MentionLike {
  id: string;
  itemId: string;
  sourceRef: {
    sourceId: string;
    episodeGuid?: string | null;
    timestamp?: string | null;
    transcriptSource?: 'youtube' | 'acast' | null;
  };
  recommendedBy?: string | null;
  quote?: string | null;
  kind: 'reco' | 'citation';
  /** Miroir du flag reco `guestWork` (œuvre présentée par un·e invité·e). */
  guestWork?: boolean | null;
  status: 'draft' | 'validated' | 'discarded';
}

/** Snapshot minimal d'un Épisode (collection `episodes`). */
export interface EpisodeLike {
  guid: string;
  title: string;
  youtubeTitle?: string;
  number?: number;
  season?: number;
  date?: Date;
  youtubeUrl?: string;
}

/** Une mention jointe à son épisode pour l'affichage timeline. */
export interface JoinedMention {
  mention: MentionLike;
  episode: EpisodeLike | null;
}

/** Vue agrégée d'une œuvre prête à être rendue. */
export interface WorkAggregate {
  item: ItemLike;
  /** Mentions non-discarded triées par date d'épisode DESC. */
  mentions: JoinedMention[];
  /** Nombre de mentions visibles (= mentions.length, citations incluses). */
  mentionCount: number;
  /**
   * L4 — Nombre de mentions qui sont des RECOMMANDATIONS (`kind !== 'citation'`,
   * œuvres d'invité·es incluses). Sert au libellé « Recommandée N fois » de la
   * page œuvre, qui ne doit PAS compter les simples citations. La timeline,
   * elle, continue d'afficher TOUTES les mentions (`mentions`/`mentionCount`).
   */
  recoCount: number;
  /** Trending si ≥2 mentions dans les 12 derniers mois. */
  trending: boolean;
  /** Date de mention la plus récente (utile pour SEO). */
  lastMentionedAt: Date | null;
}

/**
 * Filtre les mentions « visibles » côté public.
 * - `status === 'discarded'` → masqué (faux positif).
 * - Tout le reste (draft + validated) est conservé.
 */
export function isVisibleMention(m: MentionLike): boolean {
  return m.status !== 'discarded';
}

/**
 * Trending : ≥2 mentions visibles dans la fenêtre des `windowMonths`
 * derniers mois (12 par défaut). Les mentions sans date d'épisode connue
 * ne comptent pas dans la fenêtre temporelle mais comptent pour le total.
 */
export function isTrending(
  joinedMentions: JoinedMention[],
  now: Date = new Date(),
  windowMonths = 12,
): boolean {
  if (joinedMentions.length < 2) return false;
  const cutoff = new Date(now);
  cutoff.setMonth(cutoff.getMonth() - windowMonths);
  const recent = joinedMentions.filter((jm) => {
    const d = jm.episode?.date;
    return d instanceof Date && !Number.isNaN(d.getTime()) && d >= cutoff;
  });
  return recent.length >= 2;
}

/**
 * Construit un index `itemId → WorkAggregate` pour une source.
 *
 * - On filtre les mentions sur `sourceId` et `isVisibleMention`.
 * - On joint chaque mention à son épisode via `episodeGuid` (Map O(1)).
 * - On trie les mentions par date d'épisode DESC (manquantes en queue).
 * - On n'émet que les items ayant ≥1 mention visible.
 */
export function buildWorkIndex(opts: {
  sourceId: string;
  items: ItemLike[];
  mentions: MentionLike[];
  episodes: EpisodeLike[];
  now?: Date;
}): Map<string, WorkAggregate> {
  const { sourceId, items, mentions, episodes, now = new Date() } = opts;

  const episodeByGuid = new Map<string, EpisodeLike>();
  for (const e of episodes) episodeByGuid.set(e.guid, e);

  const itemById = new Map<string, ItemLike>();
  for (const it of items) itemById.set(it.id, it);

  // Groupe les mentions visibles par itemId.
  const grouped = new Map<string, JoinedMention[]>();
  for (const m of mentions) {
    if (m.sourceRef.sourceId !== sourceId) continue;
    if (!isVisibleMention(m)) continue;
    if (!itemById.has(m.itemId)) continue;
    const episode = m.sourceRef.episodeGuid
      ? episodeByGuid.get(m.sourceRef.episodeGuid) ?? null
      : null;
    const arr = grouped.get(m.itemId) ?? [];
    arr.push({ mention: m, episode });
    grouped.set(m.itemId, arr);
  }

  const out = new Map<string, WorkAggregate>();
  for (const [itemId, joined] of grouped) {
    const item = itemById.get(itemId)!;
    // Tri par date d'épisode DESC. Mentions sans date placées en queue.
    joined.sort((a, b) => {
      const da = a.episode?.date?.getTime() ?? -Infinity;
      const db = b.episode?.date?.getTime() ?? -Infinity;
      return db - da;
    });
    const lastDate =
      joined.find((jm) => jm.episode?.date)?.episode?.date ?? null;
    // L4 : recos = tout ce qui n'est pas une citation (œuvres d'invité·es
    // incluses — elles restent des recommandations au sens catalogue).
    const recoCount = joined.filter(
      (jm) => jm.mention.kind !== 'citation',
    ).length;
    out.set(itemId, {
      item,
      mentions: joined,
      mentionCount: joined.length,
      recoCount,
      trending: isTrending(joined, now),
      lastMentionedAt: lastDate,
    });
  }
  return out;
}

/**
 * Liens externes d'une œuvre, normalisés pour affichage. Tire de
 * `item.customLinks`, `item.watchProviders` et des `externalIds` connus
 * (TMDB, Spotify, OpenLibrary, JustWatch) — sans aller chercher au-delà.
 */
export interface WorkExternalLink {
  label: string;
  url: string;
  ethics?: 'indie' | 'neutral' | 'avoid';
}

/**
 * H11-1 — Guard contre XSS DOM via les URLs fournies par le pipeline
 * (`customLinks`, `watchProviders`). On n'accepte QUE `http://` et `https://`
 * pour empêcher `javascript:`, `data:`, `vbscript:`, et autres protocoles
 * exécutables qui passeraient à travers `href={url}` Astro sans échappement.
 *
 * Renvoie `true` si l'URL est sûre et a un host non-vide.
 */
function isSafeHttpUrl(url: unknown): url is string {
  if (typeof url !== 'string' || url.length === 0) return false;
  if (!/^https?:\/\//i.test(url)) return false;
  try {
    const u = new URL(url);
    return u.hostname.length > 0;
  } catch {
    return false;
  }
}

export function workExternalLinks(item: ItemLike): WorkExternalLink[] {
  const out: WorkExternalLink[] = [];
  for (const l of item.customLinks ?? []) {
    if (!isSafeHttpUrl(l.url)) continue;
    out.push({ label: l.label, url: l.url });
  }
  for (const w of item.watchProviders ?? []) {
    if (!isSafeHttpUrl(w.url)) continue;
    out.push({
      label: w.name,
      url: w.url,
      ethics:
        w.ethics === 'indie' || w.ethics === 'avoid' ? w.ethics : 'neutral',
    });
  }
  const ext = item.externalIds ?? {};
  const tmdbId = ext.tmdb;
  const tmdbType = ext.tmdbType;
  if (typeof tmdbId === 'number' && (tmdbType === 'movie' || tmdbType === 'tv')) {
    out.push({
      label: 'TMDB',
      url: `https://www.themoviedb.org/${tmdbType}/${tmdbId}`,
    });
  }
  if (typeof ext.spotify === 'string' && ext.spotify) {
    out.push({ label: 'Spotify', url: `https://open.spotify.com/${ext.spotify}` });
  }
  if (typeof ext.openlibrary === 'string' && ext.openlibrary) {
    out.push({
      label: 'OpenLibrary',
      url: `https://openlibrary.org/works/${ext.openlibrary}`,
      ethics: 'indie',
    });
  }
  if (typeof ext.justwatch === 'string' && isSafeHttpUrl(ext.justwatch)) {
    out.push({ label: 'JustWatch', url: ext.justwatch });
  }
  // Dédup par label (case-insensitive) — customLinks gardent priorité.
  const seen = new Map<string, WorkExternalLink>();
  for (const l of out) {
    const k = l.label.toLowerCase();
    if (!seen.has(k)) seen.set(k, l);
  }
  return Array.from(seen.values());
}

/**
 * Œuvres similaires : autres items du même créateur (excluant l'item
 * courant). Limité à `limit` (3 par défaut).
 *
 * Wrapper rétro-compatible autour de `creatorBasedProvider`
 * (cf. `src/lib/work/similarity.ts` et ADR 0044). Conserve la signature
 * historique (`ItemLike[]`) pour ne pas casser les call-sites P2.11.
 * Les nouveaux consommateurs sont invités à passer par
 * `getSimilarWorksProvider(sourceId)` qui retourne `SimilarWork[]` enrichi
 * (score embeddings + `reason`).
 */
export function similarByCreator(
  current: ItemLike,
  candidates: ItemLike[],
  limit = 3,
): ItemLike[] {
  const hits = creatorBasedProvider.findSimilar(current, candidates, { limit });
  const byId = new Map<string, ItemLike>();
  for (const c of candidates) byId.set(c.id, c);
  const out: ItemLike[] = [];
  for (const h of hits) {
    const it = byId.get(h.id);
    if (it) out.push(it);
  }
  return out;
}

/**
 * Construit une URL deep-link YouTube à partir d'une mention.
 * - Si `episode.youtubeUrl` + timestamp `HH:MM:SS` → ajoute `&t=Ns`.
 * - Sinon retourne `episode.youtubeUrl` brut, ou `null` si absent.
 */
export function youtubeDeepLink(jm: JoinedMention): string | null {
  const url = jm.episode?.youtubeUrl;
  if (!url) return null;
  const ts = jm.mention.sourceRef.timestamp;
  // L'offset n'est légitime que côté YouTube (cf. politique transcripts).
  if (!ts || jm.mention.sourceRef.transcriptSource !== 'youtube') return url;
  const m = /^(\d{2}):(\d{2}):(\d{2})$/.exec(ts);
  if (!m) return url;
  const seconds = Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
  if (seconds <= 0) return url;
  return url.includes('?')
    ? `${url}&t=${seconds}s`
    : `${url}?t=${seconds}s`;
}
