/**
 * Tests i18n — clés de la page épisode (M2 : sections + ledes) et compteurs
 * d'en-tête (L1/N2). Smoke sur l'existence + interpolation `{count}`.
 *
 * On vérifie aussi les apostrophes typographiques (N1) : aucune apostrophe
 * droite (') dans les libellés de section/lede/compteur.
 */
import { describe, it, expect } from 'vitest';
import { fr } from '../../src/i18n/fr';
import { t } from '../../src/i18n';

const EPISODE_KEYS = [
  'episode.section.recommendations',
  'episode.section.guestWorks',
  'episode.section.citations',
  'episode.lede.guestWorks',
  'episode.lede.citations',
  'episode.count.recommendations.one',
  'episode.count.recommendations.many',
  'episode.count.guestWorks.one',
  'episode.count.guestWorks.many',
  'episode.count.citations.one',
  'episode.count.citations.many',
] as const;

describe('i18n FR — page épisode (M2/L1)', () => {
  it.each(EPISODE_KEYS)('clé %s existe et est non vide', (k) => {
    const v = (fr as Record<string, string>)[k];
    expect(typeof v).toBe('string');
    expect(v.length).toBeGreaterThan(0);
  });

  it.each(EPISODE_KEYS)('clé %s n’a pas d’apostrophe droite (N1)', (k) => {
    const v = (fr as Record<string, string>)[k];
    expect(v).not.toContain("'");
  });

  it('interpole {count} dans les formes plurielles', () => {
    expect(t('episode.count.recommendations.many', { count: 3 })).toBe(
      '3 recommandations',
    );
    expect(t('episode.count.guestWorks.many', { count: 2 })).toBe(
      'dont 2 œuvres présentées dans l’épisode',
    );
    expect(t('episode.count.citations.many', { count: 4 })).toBe('4 mentions');
  });
});
