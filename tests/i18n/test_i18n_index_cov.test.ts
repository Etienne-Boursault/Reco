/**
 * Tests du helper i18n (`src/i18n/index.ts`).
 *
 * Couvre les quatre signatures documentées de `t()` (clé seule, clé + locale,
 * clé + params, clé + params + locale), le repli sur la locale par défaut,
 * le comportement de l'interpolation `{var}` (variable inconnue conservée
 * telle quelle), le repli sur clé absente (jamais d'exception en plein rendu)
 * et `langToOgLocale()`.
 */
import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  afterEach,
  type MockInstance,
} from 'vitest';
import { t, langToOgLocale, defaultLocale, type Locale } from '../../src/i18n';
import { fr, type I18nKey } from '../../src/i18n/fr';

/** Clé du catalogue contenant un placeholder `{count}`. */
const KEY_WITH_COUNT: I18nKey = 'episode.count.recommendations.many';
/** Clé du catalogue contenant un placeholder `{date}`. */
const KEY_WITH_DATE: I18nKey = 'stats.generatedAt';
/** Clé sans aucun placeholder. */
const KEY_PLAIN: I18nKey = 'a11y.skipLink';
/** Clé portant DEUX placeholders distincts. */
const KEY_MULTI: I18nKey = 'work.description.reco.many';

describe('defaultLocale', () => {
  it('vaut « fr »', () => {
    expect(defaultLocale).toBe('fr');
  });
});

// ---------------------------------------------------------------------------
// t() — signature 1 : clé seule
// ---------------------------------------------------------------------------
describe('t(key)', () => {
  it('renvoie la chaîne de la locale par défaut', () => {
    expect(t(KEY_PLAIN)).toBe(fr[KEY_PLAIN]);
    expect(t(KEY_PLAIN)).toBe('Aller au contenu principal');
  });

  it('renvoie la chaîne brute, placeholders inclus, sans params', () => {
    expect(t(KEY_WITH_COUNT)).toBe(fr[KEY_WITH_COUNT]);
    expect(t(KEY_WITH_COUNT)).toContain('{count}');
  });
});

// ---------------------------------------------------------------------------
// t() — signature 2 : clé + locale explicite
// ---------------------------------------------------------------------------
describe('t(key, locale)', () => {
  it('accepte une locale explicite en 2e argument', () => {
    expect(t(KEY_PLAIN, 'fr')).toBe(fr[KEY_PLAIN]);
  });

  it('retombe sur « fr » quand la locale demandée n’existe pas', () => {
    // Repli documenté (« Si la locale demandée n'existe pas, on retombe sur
    // fr »). Le kit n'embarque qu'une locale : on force le cas via un cast,
    // faute de quoi la branche `?? locales[defaultLocale]` serait morte.
    const unknown = 'en' as Locale;
    expect(t(KEY_PLAIN, unknown)).toBe(fr[KEY_PLAIN]);
  });

  it('retombe sur « fr » aussi avec interpolation', () => {
    const unknown = 'de' as Locale;
    expect(t(KEY_WITH_COUNT, { count: 5 }, unknown)).toBe('5 recommandations');
  });
});

// ---------------------------------------------------------------------------
// t() — signature 3 : clé + params (interpolation)
// ---------------------------------------------------------------------------
describe('t(key, params)', () => {
  it('interpole une variable numérique', () => {
    expect(t(KEY_WITH_COUNT, { count: 3 })).toBe('3 recommandations');
  });

  it('interpole une variable chaîne', () => {
    expect(t(KEY_WITH_DATE, { date: '12 mars 2026' })).toBe(
      'Calculé le 12 mars 2026',
    );
  });

  it('convertit la valeur en chaîne (String())', () => {
    expect(t(KEY_WITH_COUNT, { count: 0 })).toBe('0 recommandations');
  });

  it('laisse le placeholder intact si la variable manque', () => {
    expect(t(KEY_WITH_DATE, { autre: 'x' })).toBe('Calculé le {date}');
  });

  it('ignore les params en trop', () => {
    expect(t(KEY_WITH_COUNT, { count: 2, inutile: 'x' })).toBe(
      '2 recommandations',
    );
  });

  it('un objet params vide déclenche quand même l’interpolation (placeholder conservé)', () => {
    // `{}` est truthy : on passe par le remplacement, mais aucune clé ne
    // correspond → le placeholder reste tel quel.
    expect(t(KEY_WITH_DATE, {})).toBe('Calculé le {date}');
  });

  it('ne touche pas une chaîne sans placeholder', () => {
    expect(t(KEY_PLAIN, { count: 9 })).toBe('Aller au contenu principal');
  });

  it('remplace TOUS les placeholders d’une chaîne, pas seulement le premier', () => {
    // Sans le flag `g` sur la regex, seul `{count}` serait substitué et
    // `{source}` resterait affiché tel quel dans la meta description.
    expect(t(KEY_MULTI, { count: 3, source: 'Un Bon Moment' })).toBe(
      'Recommandée 3 fois dans le podcast Un Bon Moment.',
    );
  });

  it('substitue les placeholders connus et laisse les autres intacts', () => {
    expect(t(KEY_MULTI, { count: 3 })).toBe(
      'Recommandée 3 fois dans le podcast {source}.',
    );
    expect(t(KEY_MULTI, { source: 'X' })).toBe(
      'Recommandée {count} fois dans le podcast X.',
    );
  });

  it('accepte `undefined` en 2e argument (équivalent à la clé seule)', () => {
    expect(t(KEY_PLAIN, undefined)).toBe(fr[KEY_PLAIN]);
  });
});

// ---------------------------------------------------------------------------
// t() — signature 4 : clé + params + locale
// ---------------------------------------------------------------------------
describe('t(key, params, locale)', () => {
  it('combine interpolation et locale explicite', () => {
    expect(t(KEY_WITH_COUNT, { count: 12 }, 'fr')).toBe('12 recommandations');
  });

  it('la locale passée en 3e argument est utilisée quand le 2e est un objet', () => {
    expect(t(KEY_WITH_DATE, { date: 'hier' }, 'fr')).toBe('Calculé le hier');
  });
});

// ---------------------------------------------------------------------------
// Robustesse
// ---------------------------------------------------------------------------
describe('t() — clé absente du catalogue', () => {
  /** Chaque cas utilise une clé DISTINCTE : l'avertissement est dédupliqué
   *  au niveau du module et ne se rejoue pas pour une clé déjà signalée. */
  let warn: MockInstance<typeof console.warn>;

  beforeEach(() => {
    warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    warn.mockRestore();
  });

  it('renvoie la clé elle-même, sans params', () => {
    const missing = 'absente.sans.params' as I18nKey;
    expect(t(missing)).toBe('absente.sans.params');
  });

  it('renvoie la clé elle-même AVEC params (comportement uniforme)', () => {
    const missing = 'absente.avec.params' as I18nKey;
    expect(t(missing, { count: 1 })).toBe('absente.avec.params');
  });

  it('renvoie la même valeur avec et sans params', () => {
    const missing = 'absente.uniforme' as I18nKey;
    expect(t(missing, { count: 1 })).toBe(t(missing));
  });

  it('ne lève jamais, quelle que soit la forme de l’appel', () => {
    const missing = 'absente.jamais.leve' as I18nKey;
    expect(() => t(missing)).not.toThrow();
    expect(() => t(missing, { count: 1 })).not.toThrow();
    expect(() => t(missing, 'fr')).not.toThrow();
    expect(() => t(missing, { count: 1 }, 'fr')).not.toThrow();
    expect(() => t(missing, undefined)).not.toThrow();
  });

  it('ne lève pas non plus sur une clé vide', () => {
    const empty = '' as I18nKey;
    expect(() => t(empty)).not.toThrow();
    expect(() => t(empty, { count: 1 })).not.toThrow();
    expect(t(empty)).toBe('');
  });

  it('ne lève pas sur une clé héritée d’Object.prototype', () => {
    // `locales.fr['toString']` renvoie une FONCTION, pas `undefined` : une
    // garde `=== undefined` ne suffirait pas et `raw.replace` casserait.
    const proto = 'toString' as I18nKey;
    expect(() => t(proto, { count: 1 })).not.toThrow();
    expect(t(proto)).toBe('toString');
  });

  it('ne lève pas non plus sur une locale inconnue + clé absente', () => {
    const missing = 'absente.locale.inconnue' as I18nKey;
    expect(t(missing, 'en' as Locale)).toBe('absente.locale.inconnue');
  });

  it('avertit en console pour une clé absente', () => {
    t('absente.avertit' as I18nKey);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0][0])).toContain('absente.avertit');
  });

  it('n’avertit qu’UNE fois par clé, même sur plusieurs rendus', () => {
    const missing = 'absente.une.seule.fois' as I18nKey;
    t(missing);
    t(missing);
    t(missing, { count: 1 });
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it('n’avertit pas pour une clé présente', () => {
    t(KEY_PLAIN);
    t(KEY_WITH_COUNT, { count: 1 });
    expect(warn).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// langToOgLocale
// ---------------------------------------------------------------------------
describe('langToOgLocale', () => {
  it('mappe « fr » vers « fr_FR »', () => {
    expect(langToOgLocale('fr')).toBe('fr_FR');
  });

  it('mappe la locale par défaut', () => {
    expect(langToOgLocale(defaultLocale)).toBe('fr_FR');
  });

  it('retombe sur « fr_FR » pour une locale hors table', () => {
    // Même remarque que plus haut : une seule locale existe, la branche
    // `?? 'fr_FR'` n'est atteignable qu'en forçant le type.
    expect(langToOgLocale('es' as Locale)).toBe('fr_FR');
  });

  it('renvoie un format og:locale valide (xx_XX)', () => {
    expect(langToOgLocale('fr')).toMatch(/^[a-z]{2}_[A-Z]{2}$/);
  });
});
