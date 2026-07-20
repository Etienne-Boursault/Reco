/**
 * src/lib/tracking/types.ts — Types du domaine « tracking clics sortants ».
 *
 * Cf. ADR 0046. Le format JSONL persisté (une ligne par clic) est partagé
 * entre :
 *  - l'endpoint `/api/click` (écriture),
 *  - le CLI `tools/aggregate_clicks.py` (lecture/agrégation).
 *
 * Privacy-first (cohérent ADR 0034) : aucune IP en clair, aucun cookie,
 * aucun fingerprint. Le `ipHash` n'existe que pour le rate-limit in-memory ;
 * il n'est PAS persisté.
 */

export const CLICK_CATEGORIES = [
  'tmdb',
  'spotify',
  'imdb',
  'youtube',
  'library',
  'other',
] as const;
export type ClickCategory = (typeof CLICK_CATEGORIES)[number];

/** Événement persisté (1 ligne JSONL). */
export interface ClickEvent {
  /** ISO8601 UTC. */
  ts: string;
  /** URL externe cible (validée http(s), max 2048 chars). */
  url: string;
  category: ClickCategory;
  sourceId: string;
  /** `null` si l'élément cliqué n'est pas associé à une reco précise. */
  recoId: string | null;
  /** Référent de la page (path uniquement, pas le query — privacy). */
  ref: string | null;
  /**
   * Réservé (R-P2-19) — cohorte optionnelle (max 32 chars slug). Pas encore
   * exposé côté API publique ; le champ est accepté lors de la lecture JSONL
   * pour rester forward-compatible si on enrichit plus tard.
   */
  cohort?: string | null;
}

/** Limites de validation (réutilisées endpoint + CLI). */
export const CLICK_LIMITS = {
  urlMax: 2048,
  refMax: 512,
  slugMax: 128,
  cohortMax: 32,
} as const;

/**
 * Protocol minimal d'écriture pour `handleClick` (R-P1-14).
 *
 * Permet l'injection de dépendance : par défaut `JsonlClickStorage` (fs),
 * mais on peut substituer un mock en test ou un backend différent
 * (DuckDB, ClickHouse…) plus tard sans modifier le handler.
 */
export interface ClickStorage {
  append(event: ClickEvent): void;
}
