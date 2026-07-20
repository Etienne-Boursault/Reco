/**
 * src/lib/reports/types.ts — Types du domaine « signalements visiteurs ».
 *
 * Cf. ADR 0034. Le format JSON persisté est partagé entre :
 *  - l'endpoint `/api/report` (écriture),
 *  - la queue admin `/[source]/reports` (lecture build-time),
 *  - le CLI `tools/manage_reports.py` (lecture/écriture).
 *
 * Toute évolution du schéma → bump dans le ADR + helpers de migration côté CLI.
 */

export const REPORT_CATEGORIES = [
  'error',
  'inappropriate',
  'suggestion',
  'broken-link',
] as const;
export type ReportCategory = (typeof REPORT_CATEGORIES)[number];

export const REPORT_STATUSES = ['pending', 'resolved', 'dismissed'] as const;
export type ReportStatus = (typeof REPORT_STATUSES)[number];

export interface ReportSubmitter {
  /** Optionnel, ≤ 80 chars. */
  name?: string;
  /** Optionnel, validé via regex basique. */
  email?: string;
  /** Le visiteur souhaite être crédité comme contributeur·rice. */
  wantCredit: boolean;
}

export interface Report {
  /** `rep-<uuid-v4>` (préfixe pour debug grep). */
  id: string;
  sourceId: string;
  recoId: string;
  category: ReportCategory;
  /** Texte libre, ≤ 1000 chars, trim+normalisé. */
  details: string;
  submitter: ReportSubmitter;
  /** ISO8601 UTC. */
  submittedAt: string;
  status: ReportStatus;
  resolvedAt: string | null;
  resolvedBy: string | null;
  notes: string | null;
}

/** Limites de validation (réutilisées form + endpoint + CLI). */
export const REPORT_LIMITS = {
  detailsMax: 1000,
  nameMax: 80,
  emailMax: 254,
  notesMax: 500,
} as const;
