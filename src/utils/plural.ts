/**
 * src/utils/plural.ts — Helper de pluralisation français minimal.
 *
 * N7 : les descriptions meta construites inline (« 1 recommandations
 * extraites… ») accordaient mal le nom au nombre. En français, le pluriel
 * s'applique dès `n >= 2` (0 et 1 → singulier). Ce helper renvoie la forme
 * correcte sans embarquer de lib i18n (cf. ADR 0026 — kit duplicable).
 *
 * Pour les libellés traduits, préférer les clés i18n `.one` / `.many`
 * (cf. `src/i18n/fr.ts`). Ce helper cible les chaînes composées à la volée
 * (meta description SEO) où une clé i18n serait surdimensionnée.
 */

/**
 * Renvoie `singular` si `count < 2`, sinon la forme plurielle. Par défaut le
 * pluriel = `singular + 's'` ; passer `pluralForm` pour les cas irréguliers.
 *
 * @example plural(1, 'recommandation')        // 'recommandation'
 * @example plural(3, 'recommandation')        // 'recommandations'
 * @example plural(2, 'travail', 'travaux')    // 'travaux'
 */
export function plural(count: number, singular: string, pluralForm?: string): string {
  return count >= 2 ? (pluralForm ?? `${singular}s`) : singular;
}
