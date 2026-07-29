/**
 * src/lib/reports/validation.ts — Validation Zod du payload `/api/report`.
 *
 * Source de vérité unique : tout consommateur (endpoint, tests, future
 * réutilisation côté form-builder) importe `reportPayloadSchema` ici.
 *
 * Règles :
 *  - `sourceId`/`recoId` : slugs (kebab-case alphanumérique), ≤
 *    `REPORT_LIMITS.slugMax`. Pas de validation contre `getCollection()` ici
 *    (on évite la dépendance ; le handler peut vérifier l'existence si besoin).
 *    La borne de longueur est la MÊME que celle de `storage.assertSlug` : sans
 *    elle, un slug trop long passait Zod, brûlait le jti du captcha, puis
 *    échouait à l'écriture en 500 au lieu d'un 400.
 *  - `details` : trim, ≤ 1000 chars, ≥ 5 chars (anti-blank).
 *  - `submitter.email` : regex basique `^[^@\s]+@[^@\s]+\.[^@\s]+$`. Pas de
 *    full RFC ⇒ accepte les cas raisonnables sans bloquer les visiteurs.
 *  - `submitter.name` : ≤ 80 chars trimmé.
 *  - `wantCredit` : checkbox HTML ⇒ accepte `'on'` / `true` / absent.
 */

import { z } from 'astro/zod';
import { REPORT_CATEGORIES, REPORT_LIMITS } from './types.js';

const _EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const _SLUG_RE = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/i;

// HTML checkbox sérialise à `'on'` quand cochée, absent sinon. On normalise.
//
// NB : PAS de `.optional()` sur ce schéma. `z.undefined()` fait déjà partie de
// l'union, donc une clé absente est acceptée ET traverse le `transform` → on
// obtient `false`. Ajouter `.optional()` par-dessus ferait court-circuiter le
// `transform` par Zod et rendrait `wantCredit` `undefined` alors que le type
// `ReportPayload` annonce un booléen.
const checkbox = z
  .union([z.literal('on'), z.literal('true'), z.literal(true), z.literal(false), z.undefined(), z.literal('')])
  .transform((v) => v === 'on' || v === 'true' || v === true);

export const reportPayloadSchema = z
  .object({
    sourceId: z
      .string()
      .max(REPORT_LIMITS.slugMax, 'sourceId trop long')
      .regex(_SLUG_RE, 'sourceId invalide'),
    recoId: z
      .string()
      .max(REPORT_LIMITS.slugMax, 'recoId trop long')
      .regex(_SLUG_RE, 'recoId invalide'),
    category: z.enum(REPORT_CATEGORIES),
    details: z
      .string()
      .transform((s) => s.trim())
      .pipe(
        z
          .string()
          .min(5, 'détails trop courts')
          .max(REPORT_LIMITS.detailsMax, 'détails trop longs'),
      ),
    name: z
      .string()
      .max(REPORT_LIMITS.nameMax)
      .transform((s) => s.trim())
      .optional()
      .or(z.literal('')),
    email: z
      .string()
      .max(REPORT_LIMITS.emailMax)
      .transform((s) => s.trim())
      .refine((s) => s === '' || _EMAIL_RE.test(s), 'email invalide')
      .optional()
      .or(z.literal('')),
    wantCredit: checkbox,
    // Honeypot (H16-1) : doit être vide. Si rempli, le handler court-circuite
    // (court-circuit AVANT Zod, donc cette règle attrape juste les valeurs vides
    // attendues sur le happy path). Renommé `url_unused` pour éviter l'auto-fill
    // Chrome ; on accepte aussi l'ancien nom `website` le temps de la migration
    // (templates en cache CDN).
    url_unused: z.string().max(0).optional().or(z.literal('')),
    website: z.string().max(0).optional().or(z.literal('')),
    // Captcha (vérifiés séparément, mais on les laisse traverser Zod).
    captchaToken: z.string().min(1, 'captcha manquant'),
    captchaAnswer: z.string().min(1, 'captcha manquant'),
  })
  .strict();

export type ReportPayload = z.infer<typeof reportPayloadSchema>;

/** Validateur email standalone (utilisé par le form côté serveur pour pré-render). */
export function isEmailValid(s: string): boolean {
  return _EMAIL_RE.test(s);
}
