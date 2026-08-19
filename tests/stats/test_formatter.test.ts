/**
 * Tests pour `src/lib/stats/formatter.ts`.
 */
import { describe, expect, it } from 'vitest';
import {
  formatCompact,
  formatCount,
  formatPercent,
} from '../../src/lib/stats/formatter';

describe('formatCompact', () => {
  it('renvoie un nombre brut sous 1000', () => {
    expect(formatCompact(0)).toBe('0');
    expect(formatCompact(42)).toBe('42');
    expect(formatCompact(999)).toBe('999');
  });

  it('formate en k entre 1k et 1M', () => {
    expect(formatCompact(1000)).toBe('1k');
    expect(formatCompact(1234)).toBe('1.2k');
    expect(formatCompact(12345)).toBe('12.3k');
    expect(formatCompact(999_999)).toBe('999.9k');
  });

  it('formate en M au-dessus du million', () => {
    expect(formatCompact(1_000_000)).toBe('1M');
    expect(formatCompact(1_234_567)).toBe('1.2M');
  });

  it("retourne '0' pour les valeurs invalides", () => {
    expect(formatCompact(Number.NaN)).toBe('0');
    expect(formatCompact(-5)).toBe('0');
    expect(formatCompact(Number.POSITIVE_INFINITY)).toBe('0');
  });
});

describe('formatCount', () => {
  it('utilise la locale FR par défaut (espace insécable)', () => {
    const s = formatCount(1234);
    // toLocaleString FR insère un espace insécable U+202F entre les milliers.
    expect(s.replace(/\s/g, ' ')).toBe('1 234');
  });

  it('formate 0 et les négatifs', () => {
    expect(formatCount(0)).toBe('0');
    expect(formatCount(-5)).toBe('0');
  });

  it('tronque les décimales', () => {
    expect(formatCount(42.9)).toBe('42');
  });
});

describe('formatPercent', () => {
  it('formate une fraction en pourcentage entier', () => {
    expect(formatPercent(0)).toBe('0%');
    expect(formatPercent(0.421)).toBe('42%');
    expect(formatPercent(1)).toBe('100%');
  });

  it("retourne '0%' pour les invalides", () => {
    expect(formatPercent(Number.NaN)).toBe('0%');
    expect(formatPercent(-0.5)).toBe('0%');
  });
});

describe('libellés des mois (2026-08-19)', () => {
  it('abrège le mois et expose l’année comme groupe', async () => {
    // Le graphique affichait « 2020-02 », « 2020-05 »… : illisible sur six
    // ans. La relecture a demande « juste jan/fev/mar sous les mois » et des
    // separateurs par annee.
    const { moisEnBarre } = await import('../../src/lib/stats/formatter');
    expect(moisEnBarre('2020-02', 7)).toEqual({
      label: 'fév', value: 7, groupe: '2020',
    });
  });

  it('couvre les douze mois', async () => {
    const { moisEnBarre } = await import('../../src/lib/stats/formatter');
    const attendus = ['jan', 'fév', 'mar', 'avr', 'mai', 'jun',
                      'jui', 'aoû', 'sep', 'oct', 'nov', 'déc'];
    for (let m = 1; m <= 12; m++) {
      const mm = String(m).padStart(2, '0');
      expect(moisEnBarre(`2024-${mm}`, 1).label).toBe(attendus[m - 1]);
    }
  });

  it('laisse passer un mois illisible sans lever', async () => {
    // Donnee heritee : le champ pourrait ne pas suivre le format attendu.
    const { moisEnBarre } = await import('../../src/lib/stats/formatter');
    expect(moisEnBarre('n’importe quoi', 3)).toEqual({
      label: 'n’importe quoi', value: 3, groupe: undefined,
    });
  });

  it('rejette un numéro de mois hors bornes', async () => {
    const { moisEnBarre } = await import('../../src/lib/stats/formatter');
    expect(moisEnBarre('2024-13', 1).label).toBe('2024-13');
    expect(moisEnBarre('2024-00', 1).label).toBe('2024-00');
  });
});
