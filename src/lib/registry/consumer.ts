/**
 * src/lib/registry/consumer.ts — Côté méta-site : agrège plusieurs registries.
 *
 * Pas de SSR : le méta-site charge un fichier `meta_index.json` produit
 * au build (par `tools/build_meta.py`). Ce module expose les fonctions
 * pures de tri/agrégation utilisées par les pages `/meta/`.
 *
 * Cf. ADR 0045.
 */

import {
  tryParseRegistry,
  type RegistryDocument,
  type RegistryEntry,
} from './types.js';
// F-L-2 : SSOT helpers de tri (`frSortKey`) — on factorise plutôt que
// redéfinir un `normalizeForSort` local, ce qui garantit un ordre
// strictement identique entre `/stats` et `/meta/`.
import { frSortKey } from '../stats/slug.js';

/** Reconnaît une IPv4 ou un littéral IPv6 (entre `[...]`). */
const IPV4_RE = /^(?:\d{1,3}\.){3}\d{1,3}$/;

/**
 * Dérive un slug stable depuis une `siteUrl` (host lowercase, sans port,
 * sans `www.`). Utilisé pour les routes `/meta/podcast/[slug]`.
 *
 * F-L-3 : on rejette les IP (v4 et v6) — un méta-index ne doit pas pointer
 * vers un host non résolu / privé (DNS rebinding, exposition labo). On
 * retombe sur le fallback `unknown` qui sera filtré côté agrégateur.
 */
export function slugFromSiteUrl(siteUrl: string): string {
  try {
    const u = new URL(siteUrl);
    let host = u.hostname.toLowerCase().replace(/^www\./, '');
    // IPv6 brut → `URL.hostname` renvoie `[::1]` ; on dégrade en `unknown`.
    if (host.startsWith('[') && host.endsWith(']')) return 'unknown';
    if (IPV4_RE.test(host)) return 'unknown';
    if (host) return host;
  } catch {
    // fallthrough
  }
  // Fallback déterministe pour les inputs non-URL — utile en test.
  // M24-11 : on garantit un slug non-vide (`unknown`) pour permettre la
  // construction d'une route `/slug` sans collision avec la racine.
  const cleaned = String(siteUrl ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9.-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return cleaned || 'unknown';
}

/**
 * Normalise une chaîne pour un tri déterministe (L24-23).
 * F-L-2 : délégué à `frSortKey` (SSOT, stats/slug.ts).
 */
function normalizeForSort(s: string): string {
  return frSortKey(s);
}

/** Entrée brute du meta_index : { sourceUrl, registry } sans `slug`. */
export interface RawMetaEntry {
  sourceUrl: string;
  registry: unknown;
}

/**
 * Construit la liste d'entrées validées depuis le contenu brut du
 * `meta_index.json`. Les entrées invalides sont ignorées (best-effort)
 * et reportées via `onInvalid` (callback de log facultative).
 */
export function buildEntries(
  raw: RawMetaEntry[],
  onInvalid?: (sourceUrl: string, error: string) => void,
): RegistryEntry[] {
  const out: RegistryEntry[] = [];
  for (const item of raw) {
    const parsed = tryParseRegistry(item.registry);
    if (!parsed.ok) {
      onInvalid?.(item.sourceUrl, parsed.error);
      continue;
    }
    out.push({
      sourceUrl: item.sourceUrl,
      slug: slugFromSiteUrl(parsed.value.siteUrl),
      registry: parsed.value,
    });
  }
  return dedupeBySlug(out);
}

/**
 * Élimine les doublons par `slug` — conserve la 1ʳᵉ entrée vue.
 *
 * F-H-13 : on trie d'abord par `sourceUrl` ascendant pour garantir un
 * ordre déterministe entre runs (sinon, l'ordre d'arrivée des entrées —
 * Promise.all, JSON parse — pouvait sélectionner deux URLs différentes
 * pour le même slug selon le runtime). Le tri n'altère pas la sémantique
 * « premier vu gagne » ; il la fixe.
 */
export function dedupeBySlug(entries: RegistryEntry[]): RegistryEntry[] {
  const sorted = [...entries].sort((a, b) => a.sourceUrl.localeCompare(b.sourceUrl));
  const seen = new Set<string>();
  const out: RegistryEntry[] = [];
  for (const e of sorted) {
    if (seen.has(e.slug)) continue;
    seen.add(e.slug);
    out.push(e);
  }
  return out;
}

/**
 * Trie les entrées pour la grille méta — par défaut, du plus actif au moins
 * actif (mentionsCount desc), avec tie-break alphabétique sur le titre.
 */
export function sortEntries(entries: RegistryEntry[]): RegistryEntry[] {
  return [...entries].sort((a, b) => {
    const dm = b.registry.stats.mentionsCount - a.registry.stats.mentionsCount;
    if (dm !== 0) return dm;
    return normalizeForSort(a.registry.podcast.title).localeCompare(
      normalizeForSort(b.registry.podcast.title),
      'fr',
    );
  });
}

/** Cherche une entrée par slug (utilisé par `/meta/podcast/[slug]`). */
export function findEntry(
  entries: RegistryEntry[],
  slug: string,
): RegistryEntry | undefined {
  return entries.find((e) => e.slug === slug);
}

/** Agrège des compteurs globaux sur l'ensemble du méta-index. */
export function aggregateTotals(entries: RegistryEntry[]): {
  podcasts: number;
  items: number;
  mentions: number;
  episodes: number;
  guests: number;
} {
  return entries.reduce(
    (acc, e) => {
      acc.items += e.registry.stats.itemsCount;
      acc.mentions += e.registry.stats.mentionsCount;
      acc.episodes += e.registry.stats.episodesCount;
      acc.guests += e.registry.stats.guestsCount;
      return acc;
    },
    { podcasts: entries.length, items: 0, mentions: 0, episodes: 0, guests: 0 },
  );
}

/** Re-export pour les pages `/meta/`. */
export type { RegistryDocument, RegistryEntry };
