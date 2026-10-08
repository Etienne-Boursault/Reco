/**
 * tests/og/test_etiquette.test.ts
 *
 * Gabarit « Étiquette » (`src/lib/og/etiquette.ts`) : choix des tailles de
 * titre et de chiffre, et structure de l'arbre Satori.
 */
import { describe, expect, it } from 'vitest';

import { etiquetteTemplate, lignesTitre, tailleChiffre, tailleTitre } from '../../src/lib/og/etiquette';

describe('lignesTitre', () => {
  it('un mot court tient sur une ligne', () => {
    expect(lignesTitre('Bref', 220)).toBe(1);
  });

  it('un long titre passe sur plusieurs lignes à grande taille', () => {
    expect(lignesTitre('Babor et Jenny Letellier irremplaçables', 104)).toBeGreaterThanOrEqual(2);
  });
});

describe('tailleTitre', () => {
  it('un titre court prend la plus grande taille', () => {
    expect(tailleTitre('Bref', 300)).toEqual({ taille: 220, texte: 'Bref' });
  });

  it('un titre plus long descend de taille sans être tronqué', () => {
    const r = tailleTitre('Babor et Jenny Letellier irremplaçables', 300);
    expect(r.texte).toBe('Babor et Jenny Letellier irremplaçables');
    expect(r.taille).toBeLessThan(220);
  });

  it('un titre démesuré est raccourci au mot, avec des points de suspension', () => {
    const long = 'Mot '.repeat(80).trim();
    const r = tailleTitre(long, 160);
    expect(r.taille).toBe(72);
    expect(r.texte.endsWith('…')).toBe(true);
    expect(lignesTitre(r.texte, 72) * 72 * 0.9).toBeLessThanOrEqual(160);
  });
});

describe('tailleChiffre', () => {
  it('plafonne les petits nombres, réduit les longs', () => {
    expect(tailleChiffre(14, 300)).toBe(300);
    expect(tailleChiffre(903, 300)).toBeLessThan(300);
    expect(tailleChiffre(1259, 300)).toBeLessThan(tailleChiffre(903, 300));
  });
});

describe('etiquetteTemplate', () => {
  const arbre = etiquetteTemplate({
    gabarit: 'etiquette',
    chiffre: 14,
    chiffreLibelle: 'mentions',
    rubrique: 'Série',
    titre: 'Bref',
    accent: 'pas-une-couleur',
  }) as { props: { style: Record<string, unknown>; children: Array<{ props: { style: Record<string, unknown> } }> } };

  it('1200 × 630, panneau d’accent puis côté sombre', () => {
    expect(arbre.props.style.width).toBe(1200);
    expect(arbre.props.style.height).toBe(630);
    expect(arbre.props.children).toHaveLength(2);
    expect(arbre.props.children[0]!.props.style.width).toBe(420);
  });

  it('une couleur invalide retombe sur l’accent par défaut (pas d’injection CSS)', () => {
    expect(arbre.props.children[0]!.props.style.background).toMatch(/^#[0-9a-f]{3,8}$/i);
  });
});
