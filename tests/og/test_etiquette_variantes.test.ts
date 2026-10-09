/**
 * Variantes du gabarit « Étiquette » (`src/lib/og/etiquette.ts`) : chaque
 * élément facultatif de la carte, présent puis absent, et les cas limites du
 * calcul de taille du titre. Les cartes réelles n'en montrent que quelques
 * combinaisons ; une carte d'épisode et une carte d'accueil n'ont pas les mêmes.
 */
import { describe, expect, it } from 'vitest';

import { etiquetteTemplate, lignesTitre, tailleTitre } from '../../src/lib/og/etiquette';

type Noeud = { type: string; props: { style?: Record<string, unknown>; children?: unknown } };

/** Tous les nœuds de l'arbre Satori, à plat. */
function noeuds(n: unknown, acc: Noeud[] = []): Noeud[] {
  if (Array.isArray(n)) {
    n.forEach((x) => noeuds(x, acc));
  } else if (n && typeof n === 'object' && 'props' in n) {
    acc.push(n as Noeud);
    noeuds((n as Noeud).props.children, acc);
  }
  return acc;
}
const textes = (arbre: unknown) =>
  noeuds(arbre).map((x) => x.props.children).filter((c): c is string => typeof c === 'string');

describe('lignesTitre — cas limites', () => {
  it('un texte vide n’occupe aucune ligne', () => {
    expect(lignesTitre('   ', 100)).toBe(0);
  });

  it('un mot qui remplit exactement la ligne, puis un second qui passe dessous', () => {
    // « AAAA » à 10 px : 4 × 0,4 × 10 = 16 px, la largeur même de la ligne.
    expect(lignesTitre('AAAA', 10, 16)).toBe(1);
    expect(lignesTitre('AAAA AAAA', 10, 16)).toBe(2);
  });
});

describe('tailleTitre — cas limites', () => {
  it('un mot seul trop grand même à la plus petite taille reste entier', () => {
    expect(tailleTitre('Anticonstitutionnellement', 10)).toEqual({ taille: 72, texte: 'Anticonstitutionnellement' });
  });
});

describe('etiquetteTemplate — carte d’épisode complète', () => {
  const arbre = etiquetteTemplate({
    gabarit: 'etiquette',
    chiffre: 17,
    chiffreLibelle: 'recommandations',
    chiffreContexte: 'dans cet épisode',
    repere: 'S6·E1',
    rubrique: 'Épisode',
    icone: 'M4 4h16v16H4z',
    titre: 'Bref',
    sousTitre: 'avec Grand Corps Malade',
    detail: 'Diffusé en septembre 2026',
    accent: '#ffcc00',
    bg: '#101010',
    fg: '#fafafa',
  });
  const tous = noeuds(arbre);

  it('garde les couleurs valides de la source', () => {
    const panneau = (arbre as Noeud).props.children as Noeud[];
    expect(panneau[0]!.props.style!.background).toBe('#ffcc00');
    expect((arbre as Noeud).props.style!.background).toBe('#101010');
  });

  it('porte le repère, le contexte, l’icône, le sous-titre et le détail', () => {
    expect(textes(arbre)).toEqual(expect.arrayContaining(
      ['S6·E1', 'dans cet épisode', 'avec Grand Corps Malade', 'Diffusé en septembre 2026']));
    expect(tous.some((x) => x.type === 'svg')).toBe(true);
  });

  it('un titre court prend la grande taille, resserrée', () => {
    const titre = tous.find((x) => x.props.children === 'Bref')!;
    expect(titre.props.style!.fontSize).toBeGreaterThan(140);
    expect(titre.props.style!.letterSpacing).toBe(-2);
  });
});

describe('etiquetteTemplate — carte d’accueil', () => {
  const arbre = etiquetteTemplate({
    gabarit: 'etiquette',
    chiffre: 1259,
    chiffreLibelle: 'recommandations',
    rubrique: 'Podcast',
    titre: 'Une bonne reco, tout ce que les invités d’Un Bon Moment recommandent',
    liste: ['Bref', 'Pulsions', 'Kaamelott', 'Quatrième de trop'],
    piedDomaineSeul: true,
  });
  const tous = noeuds(arbre);

  it('ni repère ni icône : le chiffre descend au pied du panneau', () => {
    const panneau = ((arbre as Noeud).props.children as Noeud[])[0]!;
    expect(panneau.props.style!.justifyContent).toBe('flex-end');
    expect(tous.some((x) => x.type === 'svg')).toBe(false);
  });

  it('trois titres au plus en liste, et le seul domaine en pied', () => {
    expect(textes(arbre)).toEqual(expect.arrayContaining(['Bref', 'Pulsions', 'Kaamelott']));
    expect(textes(arbre)).not.toContain('Quatrième de trop');
  });

  it('un long titre descend sous 140 px, moins resserré', () => {
    const titre = tous.find((x) => typeof x.props.children === 'string'
      && (x.props.children as string).startsWith('Une bonne reco'))!;
    expect(titre.props.style!.fontSize).toBeLessThanOrEqual(140);
    expect(titre.props.style!.letterSpacing).toBe(-1);
  });
});
