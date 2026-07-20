/**
 * src/lib/tracking/validator.ts — Validation Zod du payload `/api/click`.
 *
 * Une seule source de vérité pour POST JSON et GET pixel.
 *
 * Règles :
 *  - `url` : http(s) only, ≤ 2048 chars.
 *  - `sourceId` / `recoId` : slugs `[a-z0-9_-]{1,128}` (recoId optionnel).
 *  - `category` : enum strict (CLICK_CATEGORIES).
 *  - `ref` : optionnel, ≤ 512 chars, on ne stocke que le path (privacy).
 *
 * Le honeypot `bot_trap` est volontairement absent du schéma : le handler
 * court-circuite AVANT Zod (cf. handler.ts), inutile de le dupliquer (M25-9).
 */

import { z } from 'astro/zod';
import { CLICK_CATEGORIES, CLICK_LIMITS } from './types.js';

// M25-10 : regex strict aligné avec storage._SLUG_GUARD_RE (defense in depth).
const _SLUG_RE = /^[a-z0-9_-]{1,128}$/i;

const httpUrl = z
  .string()
  .max(CLICK_LIMITS.urlMax, 'url trop longue')
  .refine((u) => {
    try {
      const parsed = new URL(u);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
      return false;
    }
  }, 'url invalide (http(s) requis)');

// M25-11 : `.max(slugMax)` redondant avec la regex bornée mais documenté
// comme défense en profondeur (un futur changement de regex ne pourrait pas
// rallonger sans toucher aussi la borne).
const slug = z
  .string()
  .max(CLICK_LIMITS.slugMax, 'slug trop long')
  .regex(_SLUG_RE, 'slug invalide');

export const clickPayloadSchema = z
  .object({
    url: httpUrl,
    category: z.enum(CLICK_CATEGORIES),
    sourceId: slug,
    recoId: slug.optional().nullable(),
    ref: z.string().max(CLICK_LIMITS.refMax, 'ref trop long').optional().nullable(),
  })
  .strict();

export type ClickPayload = z.infer<typeof clickPayloadSchema>;

/**
 * Schéma de lecture JSONL (storage.readDailyEvents) — plus permissif que
 * le schéma payload, mais valide la forme essentielle pour éviter qu'une
 * ligne malformée ne pollue les agrégations (M25-15).
 */
export const clickEventSchema = z
  .object({
    ts: z.string().min(1).max(64),
    url: z.string().max(CLICK_LIMITS.urlMax),
    category: z.enum(CLICK_CATEGORIES),
    sourceId: slug,
    recoId: slug.nullable().optional(),
    ref: z.string().max(CLICK_LIMITS.refMax).nullable().optional(),
    cohort: z
      .string()
      .max(CLICK_LIMITS.cohortMax)
      .regex(_SLUG_RE, 'cohort invalide')
      .nullable()
      .optional(),
  })
  .passthrough();

/**
 * B-NIT-10 : `sanitizeAbsoluteRef` — réduit une URL absolue à son path
 * (sans query, sans hash). Retourne `null` si parse échoue.
 */
function sanitizeAbsoluteRef(cleaned: string): string | null {
  try {
    const u = new URL(cleaned);
    return (u.pathname || '/').replace(/\x00/g, '');
  } catch {
    return null;
  }
}

/**
 * B-NIT-10 : `sanitizeRelativeRef` — accepte un path relatif raisonnable
 * (commence par `/`, longueur ≤ refMax). Retourne `null` sinon.
 */
function sanitizeRelativeRef(cleaned: string): string | null {
  if (cleaned.startsWith('/') && cleaned.length <= CLICK_LIMITS.refMax) return cleaned;
  return null;
}

/**
 * Réduit un référent à son `path` (pas de query/hash). On ne veut PAS
 * persister les query strings (UTM, tokens, etc.) — privacy by design.
 *
 * L25-29 : strip les NULL bytes (\x00) pour neutraliser un injection
 * potentielle dans les logs ou agrégations downstream.
 *
 * B-NIT-10 : façade sur `sanitizeAbsoluteRef` + `sanitizeRelativeRef`.
 */
export function sanitizeRef(ref: string | null | undefined): string | null {
  if (!ref) return null;
  const cleaned = ref.replace(/\x00/g, '');
  if (!cleaned) return null;
  return sanitizeAbsoluteRef(cleaned) ?? sanitizeRelativeRef(cleaned);
}
