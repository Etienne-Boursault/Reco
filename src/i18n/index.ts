/**
 * src/i18n/index.ts — Helpers i18n minimaux.
 *
 * On n'embarque pas de framework i18n (kit duplicable, 1 locale par déploiement
 * en général). On expose juste un `t()` typé sur la locale active.
 *
 * Convention : la locale par défaut est `fr`. Une source peut surcharger via
 * `source.data.lang` (champ optionnel, non strict dans le schema). Si la
 * locale demandée n'existe pas, on retombe sur `fr`.
 */
import { fr, type I18nKey } from './fr';

const locales = { fr } as const;
export type Locale = keyof typeof locales;

/** Locale active par défaut (overridable via Layout `lang` prop). */
export const defaultLocale: Locale = 'fr';

/**
 * Récupère une chaîne traduite, avec interpolation `{var}` style mustache léger.
 *
 * Signatures supportées (compat ascendante) :
 *   t('a11y.skipLink')                          // simple
 *   t('a11y.skipLink', 'fr')                    // locale explicite
 *   t('work.stats.reco.many', { count: 3 })     // interpolation
 *   t('work.stats.reco.many', { count: 3 }, 'fr') // les deux
 */
export function t(
  key: I18nKey,
  paramsOrLocale?: Record<string, string | number> | Locale,
  locale: Locale = defaultLocale,
): string {
  let params: Record<string, string | number> | undefined;
  let loc: Locale = locale;
  if (typeof paramsOrLocale === 'string') {
    loc = paramsOrLocale;
  } else if (paramsOrLocale) {
    params = paramsOrLocale;
  }
  const raw = (locales[loc] ?? locales[defaultLocale])[key];
  if (!params) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, k) =>
    params && k in params ? String(params[k]) : `{${k}}`,
  );
}

/** Convertit un code locale (`fr`) en og:locale (`fr_FR`). */
export function langToOgLocale(locale: Locale): string {
  const map: Record<Locale, string> = { fr: 'fr_FR' };
  return map[locale] ?? 'fr_FR';
}
